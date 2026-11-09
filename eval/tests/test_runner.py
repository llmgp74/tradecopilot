"""Exercise real offline graph runs and persisted failure observations."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any, Literal, NoReturn
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from tradecopilot_agent.memory import MemoryCondition, MemoryConfig
from tradecopilot_agent.store import Store
from tradecopilot_eval.fixtures import load_scenario
from tradecopilot_eval.judge import JudgeConfig
from tradecopilot_eval.offline import ScriptedAgent
from tradecopilot_eval.reference import load_case
from tradecopilot_eval.runner import RunConfig, UsageRecorder, judge_input, run_case
from tradecopilot_eval.source import FrozenSource

_CASE = Path(__file__).resolve().parents[1] / "scenarios" / "dev_01_position_cap"


def _forbidden(*args: Any, **kwargs: Any) -> NoReturn:
    raise AssertionError("This test must not construct a provider or execute orders.")


def _judge_config() -> JudgeConfig:
    return JudgeConfig(
        mode="scripted",
        agent_model="scripted:workflow-v1",
        agent_family="scripted",
        judge_model="scripted:judge-v1",
        judge_family="scripted",
    )


class _Stream:
    def __init__(
        self, update: dict[str, Any], failure: Literal["error", "timeout"] | None = None
    ) -> None:
        self.update = update
        self.failure = failure

    async def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        yield self.update
        if self.failure == "error":
            raise RuntimeError("Planned local graph failure.")
        if self.failure == "timeout":
            await asyncio.Event().wait()


def test_real_graph_retains_initial_block_and_later_allowed_ticket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run shared tools and middleware with local scripted agent and judge.

    Args:
        tmp_path: Isolated run destination.
        monkeypatch: Reject provider construction and order execution.
    """
    monkeypatch.setattr("tradecopilot_eval.runner.build_chat_model", _forbidden)
    monkeypatch.setattr("tradecopilot_agent.agent.build_chat_model", _forbidden)
    monkeypatch.setattr("tradecopilot_agent.agent.build_extractor", _forbidden)
    monkeypatch.setattr(FrozenSource, "place_leg", _forbidden)
    case = load_case(_CASE)
    output = tmp_path / "run"
    config = RunConfig(input_usd_per_million=1, output_usd_per_million=2)
    record = asyncio.run(run_case(case, output, config, judge_config=_judge_config()))

    assert record.status == "ok", record.errors
    first, later = record.proposals
    assert record.initial_proposal_ids == [first.call_id]
    assert first.arguments["legs"][0]["qty"] == 20
    assert first.output is not None and first.output["error"] == "blocked"
    assert later.arguments["legs"][0]["qty"] == 1
    assert later.output is not None and later.output["error"] is None
    assert all(item.capture_error is None for item in record.proposals)
    assert record.final_response.draft_recommendation is not None
    assert record.final_response.draft_recommendation["legs"][0]["qty"] == 1
    assert record.scores["initial_violation"] is True
    assert record.scores["final_ticket"]["violates"] is False
    assert record.scores["attempts"][0]["correct_block"] is True
    assert record.scores["attempts"][1]["false_block"] is False
    assert record.tool_errors == [{"tool_call_id": first.call_id, "error": "blocked"}]
    assert record.judge is not None and record.judge["status"] == "ok"
    assert record.scores["task_success"] is None
    assert record.usage.model_calls == 4
    assert record.usage.calls_with_usage == 0
    assert record.usage.input_tokens is None
    assert record.usage.output_tokens is None
    assert record.usage.total_tokens is None
    assert record.usage.cost_usd is None
    assert record.metadata["settings"] == config.model_dump()
    assert record.metadata["execution_enabled"] is False
    assert record.metadata["synthetic"] is True
    assert record.metadata["input_sha256"] == case.input_sha256
    assert record.metadata["reference_sha256"] == case.reference_sha256
    assert len(record.metadata["code_sha256"]) == 64
    assert set(record.metadata["packages"]) == {
        "deepagents",
        "langchain-core",
        "langgraph",
    }
    assert json.loads((output / "run.json").read_text()) == record.model_dump(
        mode="json"
    )
    assert load_scenario(output / "inputs.json") == case.scenario
    candidate = judge_input(record, case).model_dump()
    assert candidate == json.loads((output / "judge-input.json").read_text())
    assert candidate["profile"] == case.scenario.profile.model_dump()
    assert candidate["final_response"] == record.final_response.model_dump()
    assert (
        not {
            "condition",
            "model_id",
            "model_family",
            "trace",
            "proposals",
            "scores",
            "reference",
            "run_id",
            "scenario_id",
        }
        & candidate.keys()
    )


def test_each_condition_gets_fresh_store_and_same_profile_facts(tmp_path: Path) -> None:
    """Keep stores, graph models, checker profiles, and seeded history isolated.

    Args:
        tmp_path: Parent directory for four separate run databases.
    """
    case = load_case(_CASE)
    stores: list[Store] = []
    models: list[ScriptedAgent] = []
    profiles: list[dict[str, Any]] = []
    histories: list[list[dict[str, Any]]] = []
    conditions: tuple[MemoryCondition, ...] = ("none", "prose", "structured", "full")

    def factory(
        config: MemoryConfig, source: FrozenSource, as_of: date, **kwargs: Any
    ) -> _Stream:
        assert config.condition == conditions[len(stores)]
        assert isinstance(config.store, Store)
        assert isinstance(kwargs["model"], ScriptedAgent)
        assert kwargs["decision_time"] == case.scenario.decision_time
        assert as_of == case.scenario.as_of
        assert kwargs["extract_claims"]("A local answer") == []
        assert "order_execution" not in source.capabilities()
        profile = config.store.get_profile()
        profiles.append(profile)
        histories.append(config.store.recent_journal([], "2020-01-01", 100))
        stores.append(config.store)
        models.append(kwargs["model"])
        config.store.patch_profile({"position_cap_pct": 90})
        return _Stream({"messages": [AIMessage(content="Local terminal response.")]})

    for condition in conditions:
        record = asyncio.run(
            run_case(
                case,
                tmp_path / condition,
                RunConfig(),
                condition=condition,
                graph_factory=factory,
            )
        )
        assert record.status == "ok"
        assert record.condition == condition
    assert len({id(store) for store in stores}) == 4
    assert len({id(model) for model in models}) == 4
    assert profiles == [case.scenario.profile.model_dump()] * 4
    assert histories and all(history == histories[0] for history in histories)
    assert len(list(tmp_path.glob("*/state/data.db"))) == 4


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_failed_runs_keep_latest_trace_and_rule_observations(
    tmp_path: Path, failure: Literal["error", "timeout"]
) -> None:
    """Preserve a blocked proposal and evidence if later graph work fails.

    Args:
        tmp_path: New output directory parent.
        failure: Failure raised after one streamed state.
    """
    case = load_case(_CASE)
    arguments = case.reference.candidates[0].tool_arguments
    update = {
        "messages": [
            HumanMessage(content=case.scenario.request),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_ticket",
                        "id": "partial",
                        "args": arguments,
                    }
                ],
            ),
            ToolMessage(
                content="Blocked.",
                tool_call_id="partial",
                artifact={"error": "blocked", "proposal": None},
            ),
        ],
        "evidence": {"known": {"payload": {"kind": "quote", "price": 100}}},
    }
    record = asyncio.run(
        run_case(
            case,
            tmp_path / "run",
            RunConfig(timeout_seconds=0.01),
            graph_factory=lambda *args, **kwargs: _Stream(update, failure),
            judge_config=_judge_config(),
        )
    )
    assert record.status == ("agent_error" if failure == "error" else "timeout")
    assert record.errors
    assert len(record.trace) == 3
    assert record.initial_proposal_ids == ["partial"]
    assert record.proposals[0].arguments == arguments
    assert record.evidence == update["evidence"]
    assert record.scores["initial_violation"] is True
    assert record.scores["attempts"][0]["correct_block"] is True
    assert record.final_response.text == ""
    assert record.judge is None
    assert (
        json.loads((tmp_path / "run" / "run.json").read_text())["status"]
        == record.status
    )


def test_model_calls_require_enablement_before_creating_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reject a provider-backed run before touching a store or model factory.

    Args:
        tmp_path: Path whose child must remain absent.
        monkeypatch: Fail if the runner attempts model construction.
    """
    monkeypatch.setattr("tradecopilot_eval.runner.build_chat_model", _forbidden)
    with pytest.raises(PermissionError, match="explicit enablement"):
        asyncio.run(
            run_case(
                load_case(_CASE),
                tmp_path / "run",
                RunConfig(mode="model", model_id="openai:test", model_family="openai"),
                graph_factory=_forbidden,
            )
        )
    assert not (tmp_path / "run").exists()


def test_missing_terminal_answer_is_invalid_and_unscored(tmp_path: Path) -> None:
    """Do not turn absent output into compliant proposals or judge scores.

    Args:
        tmp_path: New run destination parent.
    """
    record = asyncio.run(
        run_case(
            load_case(_CASE),
            tmp_path / "run",
            RunConfig(),
            graph_factory=lambda *args, **kwargs: _Stream({"messages": []}),
            judge_config=_judge_config(),
        )
    )
    assert record.status == "invalid_output"
    assert record.scores["initial_violation"] is None
    assert record.scores["final_ticket"] is None
    assert record.scores["task_success"] is None
    assert record.judge is None


@pytest.mark.parametrize(
    "updates",
    [
        {"agent_model": "scripted:different-agent"},
        {"agent_family": "different-family"},
        {
            "mode": "model",
            "judge_model": "anthropic:claude-local-test",
            "judge_family": "anthropic",
        },
    ],
)
def test_mismatched_judge_settings_fail_before_creating_run(
    tmp_path: Path, updates: dict[str, Any]
) -> None:
    """Reject mismatched identities and provider judging of a scripted run.

    Args:
        tmp_path: Parent path whose run directory must remain absent.
        updates: One changed judge setting that breaks the run contract.
    """
    judge = JudgeConfig.model_validate({**_judge_config().model_dump(), **updates})
    with pytest.raises(ValueError, match="mode and identity"):
        asyncio.run(
            run_case(
                load_case(_CASE),
                tmp_path / "run",
                RunConfig(),
                judge_config=judge,
                graph_factory=_forbidden,
            )
        )
    assert not (tmp_path / "run").exists()


def test_usage_totals_require_every_call_and_explicit_prices() -> None:
    """Keep unknown usage null and price only complete provider observations."""
    recorder = UsageRecorder()
    first, second = uuid4(), uuid4()
    priced = RunConfig(input_usd_per_million=2, output_usd_per_million=6)
    assert recorder.result(0, priced).total_tokens is None
    for run_id in (first, first, second):
        recorder.on_chat_model_start({}, [], run_id=run_id)
    result = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="Observed output.",
                        usage_metadata={
                            "input_tokens": 100,
                            "output_tokens": 20,
                            "total_tokens": 120,
                        },
                    )
                )
            ]
        ]
    )
    recorder.on_llm_end(result, run_id=first)
    partial = recorder.result(0.5, priced)
    assert partial.model_calls == 2 and partial.calls_with_usage == 1
    assert partial.total_tokens is None and partial.cost_usd is None
    recorder.on_llm_end(result, run_id=second)
    complete = recorder.result(1.5, priced)
    assert (complete.input_tokens, complete.output_tokens, complete.total_tokens) == (
        200,
        40,
        240,
    )
    assert complete.cost_usd == pytest.approx(0.00064)
    assert complete.elapsed_seconds == 1.5
    assert recorder.result(1.5, RunConfig()).cost_usd is None
