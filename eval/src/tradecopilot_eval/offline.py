"""Scripted graph rehearsal and network blocking for local evaluation checks."""

import socket
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from typing import Any, NoReturn
from unittest.mock import patch

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from tradecopilot_eval.fixtures import Scenario


@contextmanager
def offline_connections() -> Iterator[None]:
    """Reject network connections during a scripted run; restore on exit."""

    def blocked(*args: Any, **kwargs: Any) -> NoReturn:
        raise RuntimeError("Network connections are disabled in scripted evaluation.")

    with ExitStack() as stack:
        for target in (
            "socket.create_connection",
            "socket.getaddrinfo",
        ):
            stack.enter_context(patch(target, blocked))
        stack.enter_context(patch.object(socket.socket, "connect", blocked))
        stack.enter_context(patch.object(socket.socket, "connect_ex", blocked))
        yield


class ScriptedAgent(BaseChatModel):
    """Exercise real graph tools with predefined behavior, without using gold labels.

    This model gathers the supplied fixtures, tries 20 shares, then one share.
    It behaves identically in every memory condition and cannot measure memory
    quality. Its final text and judge scores are plumbing controls only.
    """

    scenario: Scenario
    _step: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "scripted-tradecopilot-evaluation"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedAgent":
        """Accept the real graph's tool schema without constructing a provider."""
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        step = self._step
        self._step += 1
        calls: list[Any] = []
        if step == 0:
            calls = [
                {
                    "name": "get_" + fixture.method,
                    "args": fixture.arguments,
                    "id": f"gather-{index}",
                    "type": "tool_call",
                }
                for index, fixture in enumerate(self.scenario.tool_fixtures[:10])
            ]
        elif step in (1, 2):
            tickers = self.scenario.profile.watchlist
            if tickers:
                calls = [
                    {
                        "name": "propose_ticket",
                        "id": f"proposal-{step}",
                        "type": "tool_call",
                        "args": {
                            "legs": [
                                {
                                    "ticker": tickers[0],
                                    "side": "buy",
                                    "qty": 20 if step == 1 else 1,
                                }
                            ],
                            "thesis": "Predefined ticket for a local workflow check.",
                            "horizon": "weeks",
                        },
                    }
                ]
        content = (
            ""
            if calls
            else (
                "Scripted check completed. The proposals above are test inputs. "
                "No investment recommendation or quality assessment was generated."
            )
        )
        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=content, tool_calls=calls))
            ]
        )
