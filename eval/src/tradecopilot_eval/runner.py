"""Isolated graph runs, blind judging, and reproducible local artifacts."""

import asyncio
import hashlib
import json
import platform
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import UUID, uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult
from pydantic import BaseModel, Field
from tradecopilot_agent import MemoryConfig, build_agent
from tradecopilot_agent.llm import build_chat_model
from tradecopilot_agent.memory import MemoryCondition
from tradecopilot_agent.prompt import SYSTEM_PROMPT

from tradecopilot_eval.fixtures import seed_store
from tradecopilot_eval.judge import (
    JudgeConfig,
    JudgeInput,
    JudgeTransport,
    LangChainJudgeTransport,
    ScriptedJudgeTransport,
    judge_candidate,
    sanitize_text,
)
from tradecopilot_eval.offline import ScriptedAgent
from tradecopilot_eval.records import RunRecord, Usage
from tradecopilot_eval.reference import Case
from tradecopilot_eval.scoring import score_run
from tradecopilot_eval.source import FrozenSource
from tradecopilot_eval.trace import (
    capture_proposals,
    response_projection,
    serialize_trace,
)

PROJECTION_VERSION = "visible-response-v1"


class RunConfig(BaseModel):
    """Explicit settings shared across memory conditions."""

    mode: Literal["scripted", "model"] = "scripted"
    model_id: str = "scripted:workflow-v1"
    model_family: str = "scripted"
    allow_model_calls: bool = False
    timeout_seconds: float = Field(default=120, gt=0)
    max_output_tokens: int = Field(default=4096, ge=256)
    recursion_limit: int = Field(default=100, ge=10)
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)


class UsageRecorder(BaseCallbackHandler):
    """Count model calls, including the shared claim extractor's model calls."""

    def __init__(self) -> None:
        """Start an empty run-local usage accumulator."""
        self.calls: set[UUID] = set()
        self.observed: dict[UUID, tuple[int, int, int]] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Count each provider/model invocation once without retaining prompts."""
        self.calls.add(run_id)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        """Collect standard LangChain usage when the provider reports it."""
        for group in response.generations:
            for generation in group:
                message = getattr(generation, "message", None)
                usage = getattr(message, "usage_metadata", None)
                if isinstance(usage, dict) and all(
                    isinstance(usage.get(key), int)
                    for key in ("input_tokens", "output_tokens", "total_tokens")
                ):
                    self.observed[run_id] = (
                        usage["input_tokens"],
                        usage["output_tokens"],
                        usage["total_tokens"],
                    )

    def result(self, elapsed: float, config: RunConfig) -> Usage:
        """Return complete totals only when every observed call has usage."""
        result = Usage(
            model_calls=len(self.calls),
            calls_with_usage=len(self.observed),
            elapsed_seconds=elapsed,
        )
        if self.calls and self.calls == set(self.observed):
            result.input_tokens = sum(item[0] for item in self.observed.values())
            result.output_tokens = sum(item[1] for item in self.observed.values())
            result.total_tokens = sum(item[2] for item in self.observed.values())
            if (
                config.input_usd_per_million is not None
                and config.output_usd_per_million is not None
            ):
                result.cost_usd = (
                    result.input_tokens * config.input_usd_per_million
                    + result.output_tokens * config.output_usd_per_million
                ) / 1_000_000
        return result


def write_json(path: Path, value: Any) -> None:
    """Write JSON atomically; callers create the destination directory first."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False, default=str)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def code_digest() -> str:
    """Hash local Python sources and dependency files, including uncommitted edits."""
    root = Path(__file__).resolve().parents[3]
    paths = [*root.glob("agent/src/**/*.py"), *root.glob("eval/src/**/*.py")]
    paths += [
        root / "uv.lock",
        root / "agent/pyproject.toml",
        root / "eval/pyproject.toml",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def judge_input(record: RunRecord, case: Case) -> JudgeInput:
    """Build a fixed blind view without run labels, raw proposals, or private traces."""
    account: dict[str, Any] = {}
    for fixture in case.scenario.tool_fixtures:
        if fixture.method == "portfolio" and fixture.output.evidence:
            account = fixture.output.evidence[0].payload
    return JudgeInput(
        sample_id=hashlib.sha256(record.run_id.encode()).hexdigest()[:20],
        request=case.scenario.request,
        decision_time=case.scenario.decision_time.isoformat(),
        profile=case.scenario.profile.model_dump(),
        portfolio=account,
        journal_before_decision=case.scenario.journal_before_decision,
        reference_evidence=[
            item.model_dump() for item in case.reference.reference_evidence
        ],
        acceptance_criteria=case.reference.response_criteria,
        final_response=record.final_response.model_dump(),
    )


def _model(config: RunConfig, case: Case, usage: UsageRecorder) -> BaseChatModel:
    if config.mode == "scripted":
        return ScriptedAgent(scenario=case.scenario, callbacks=[usage])
    if not config.allow_model_calls:
        raise PermissionError("Model calls require explicit enablement.")
    model = build_chat_model(config.model_id)
    updates: dict[str, Any] = {"callbacks": [usage]}
    fields = type(model).model_fields
    if "temperature" in fields:
        updates["temperature"] = 0
    if "max_tokens" in fields:
        updates["max_tokens"] = config.max_output_tokens
    else:
        raise ValueError("This model adapter does not expose max_tokens.")
    return model.model_copy(update=updates)


async def run_case(
    case: Case,
    output_dir: Path,
    config: RunConfig,
    *,
    condition: MemoryCondition = "full",
    phase: Literal["screening", "ablation", "single"] = "single",
    repetition: int = 1,
    judge_config: JudgeConfig | None = None,
    transport: JudgeTransport | None = None,
    graph_factory: Callable[..., Any] = build_agent,
) -> RunRecord:
    """Run one graph in a new directory and preserve errors and partial state.

    Args:
        case: Agent inputs and separate scorer references.
        output_dir: New run directory; refuses reuse.
        config: Recorded model, limits, and optional pricing assumptions.
        condition: Memory visible to the agent; the checker always sees the profile.
        phase: Separate full-system screening from repeated ablation trials.
        repetition: One-based trial number.
        judge_config: Optional blind-judge settings.
        transport: Optional injected judge caller; otherwise selected by mode.
        graph_factory: Actual shared graph by default; injectable for failure tests.

    Returns:
        A persisted run record. No execution capability is ever enabled.
        Timeouts preserve the latest streamed state. Provider-level blocking
        operations can delay cancellation; their own timeout still applies.

    Raises:
        FileExistsError: output_dir already exists.
        PermissionError: Model calls were requested without explicit enablement.
    """
    if config.mode == "model" and not config.allow_model_calls:
        raise PermissionError("Model calls require explicit enablement.")
    if judge_config is not None and (
        judge_config.mode != config.mode
        or judge_config.agent_model != config.model_id
        or judge_config.agent_family != config.model_family
    ):
        raise ValueError("Judge settings must match the agent run mode and identity.")
    output_dir.mkdir(parents=True, exist_ok=False)
    store = seed_store(case.scenario, output_dir / "state")
    source = FrozenSource(case.scenario.tool_fixtures, case.scenario.decision_time)
    run_id = uuid4().hex
    usage = UsageRecorder()
    started = perf_counter()
    state: dict[str, Any] = {"messages": [HumanMessage(content=case.scenario.request)]}
    record = RunRecord(
        run_id=run_id,
        scenario_id=case.scenario.scenario_id,
        condition=condition,
        phase=phase,
        repetition=repetition,
        mode=config.mode,
        model_id=config.model_id,
        model_family=config.model_family,
        status="ok",
        metadata={
            "started_at": datetime.now(UTC).isoformat(),
            "settings": config.model_dump(),
            "input_sha256": case.input_sha256,
            "reference_sha256": case.reference_sha256,
            "code_sha256": code_digest(),
            "projection_version": PROJECTION_VERSION,
            "agent_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
            "python": platform.python_version(),
            "packages": {
                name: version(name)
                for name in ("deepagents", "langchain-core", "langgraph")
            },
            "synthetic": case.scenario.synthetic,
            "provenance_status": case.reference.provenance_status,
            "category": case.reference.category,
            "execution_enabled": False,
            "cost_basis": (
                "supplied per-million token prices; estimate, "
                "excludes billing adjustments"
            ),
        },
    )
    if case.input_document and case.reference_document:
        (output_dir / "inputs.json").write_bytes(case.input_document)
        (output_dir / "reference.json").write_bytes(case.reference_document)
    else:
        write_json(output_dir / "inputs.json", case.scenario.model_dump(mode="json"))
        write_json(
            output_dir / "reference.json", case.reference.model_dump(mode="json")
        )
    try:
        model = _model(config, case, usage)
        graph = graph_factory(
            MemoryConfig(condition=condition, store=store),
            source,
            case.scenario.as_of,
            model=model,
            decision_time=case.scenario.decision_time,
            **(
                {"extract_claims": lambda _text: []}
                if config.mode == "scripted"
                else {}
            ),
        )
        async with asyncio.timeout(config.timeout_seconds):
            async for update in graph.astream(
                state,
                {
                    "configurable": {"thread_id": run_id},
                    "recursion_limit": config.recursion_limit,
                },
                stream_mode="values",
            ):
                state = dict(update)
    except TimeoutError:
        record.status = "timeout"
        record.errors.append("Agent exceeded the run timeout.")
    except Exception as exc:
        record.status = "agent_error"
        record.errors.append(sanitize_text(f"{type(exc).__name__}: {exc}"))
    record.usage = usage.result(perf_counter() - started, config)
    messages = list(state.get("messages", []))
    record.trace = serialize_trace(messages)
    record.proposals, record.initial_proposal_ids = capture_proposals(messages)
    record.evidence = state.get("evidence", {})
    try:
        record.final_response = response_projection(state)
        if not record.final_response.text and record.status == "ok":
            record.status = "invalid_output"
            record.errors.append("No final assistant text was returned.")
    except ValueError as exc:
        record.status = "invalid_output"
        record.errors.append(sanitize_text(str(exc)))
    record.tool_errors = [
        {
            "tool_call_id": item["data"].get("tool_call_id"),
            "error": item["data"]["artifact"]["error"],
        }
        for item in record.trace
        if item.get("type") == "tool"
        and isinstance(item.get("data", {}).get("artifact"), dict)
        and item["data"]["artifact"].get("error")
    ]
    record.scores = score_run(record, case)
    write_json(output_dir / "run.json", record.model_dump(mode="json"))
    if judge_config is not None and record.status == "ok":
        candidate = judge_input(record, case)
        write_json(output_dir / "judge-input.json", candidate.model_dump())
        caller = transport or (
            ScriptedJudgeTransport()
            if judge_config.mode == "scripted"
            else LangChainJudgeTransport(judge_config, enabled=config.allow_model_calls)
        )
        judged = await judge_candidate(candidate, caller, judge_config)
        record.judge = judged.model_dump(mode="json")
        if judged.status == "ok" and judge_config.mode == "model":
            criteria = [item.met for item in judged.criteria or []]
            final_rule = record.scores["final_ticket"]
            success: bool | None = None
            if (
                False in criteria
                or judged.outcome not in case.reference.acceptable_outcomes
            ):
                success = False
            elif criteria and None not in criteria:
                success = True
            if final_rule and final_rule["violates"] is True:
                success = False
            elif final_rule and final_rule["status"] == "unscorable" and success:
                success = None
            record.scores.update(
                task_success=success,
                outcome=judged.outcome,
                task_assessment_source="judge_assisted",
            )
        write_json(output_dir / "judge.json", record.judge)
        write_json(output_dir / "run.json", record.model_dump(mode="json"))
    return record
