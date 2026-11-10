"""General web search for the agent.

DeepSeek's Search API is used when a DeepSeek key exists. Exa is the fallback
for every other provider. With neither key, the agent has no web search tool.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

DEEPSEEK_SEARCH_URL = "https://api.deepseek.com"
EXA_SEARCH_URL = "https://api.exa.ai"
SEARCH_TIMEOUT_SECONDS = 15.0
DEFAULT_RESULTS = 8


class WebSearchUnavailable(Exception):
    """The configured search provider could not answer."""


@dataclass(frozen=True)
class WebResult:
    """One web search result with provenance.

    Attributes:
        title: Page title.
        url: Page URL.
        summary: Excerpt or summary suitable for the model.
        published_at: Publication timestamp, ISO 8601, when the provider
            supplies one.
        source: Provider id, ``deepseek_search`` or ``exa_search``.
        authority: Provider authority tier, when supplied.
    """

    title: str
    url: str
    summary: str
    published_at: str | None
    source: str
    authority: int | None = None


class WebSearch(Protocol):
    """A provider-neutral web search."""

    async def search(self, query: str, count: int = DEFAULT_RESULTS) -> list[WebResult]:
        """Return ranked results for a query."""
        ...


class DeepSeekWebSearch:
    """DeepSeek's in-house web search."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEEPSEEK_SEARCH_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Bind the API key and optional test transport.

        Args:
            api_key: DeepSeek bearer key.
            base_url: API base URL.
            transport: Optional HTTP transport for tests.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.transport = transport

    async def search(self, query: str, count: int = DEFAULT_RESULTS) -> list[WebResult]:
        """Search the web through DeepSeek.

        Args:
            query: Natural language query.
            count: Number of results to request.

        Returns:
            Ranked results.

        Raises:
            WebSearchUnavailable: When the request fails or returns bad data.
        """
        payload = {"query": query, "count": count, "need_content": False}
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=SEARCH_TIMEOUT_SECONDS,
                transport=self.transport,
            ) as client:
                response = await client.post("/v1/tools/search", json=payload)
                response.raise_for_status()
                data = response.json()
            items = data["results"]
            return [_deepseek_result(item) for item in items][:count]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise WebSearchUnavailable("Web search failed.") from exc


class ExaWebSearch:
    """Exa neural search, used when no DeepSeek key exists."""

    def __init__(
        self,
        api_key: str,
        base_url: str = EXA_SEARCH_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Bind the API key and optional test transport.

        Args:
            api_key: Exa bearer key.
            base_url: API base URL.
            transport: Optional HTTP transport for tests.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.transport = transport

    async def search(self, query: str, count: int = DEFAULT_RESULTS) -> list[WebResult]:
        """Search the web through Exa.

        Args:
            query: Natural language query.
            count: Number of results to request.

        Returns:
            Ranked results.

        Raises:
            WebSearchUnavailable: When the request fails or returns bad data.
        """
        payload = {
            "query": query,
            "numResults": count,
            "type": "auto",
            "contents": {"highlights": True},
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=SEARCH_TIMEOUT_SECONDS,
                transport=self.transport,
            ) as client:
                response = await client.post("/search", json=payload)
                response.raise_for_status()
                data = response.json()
            items = data["results"]
            return [_exa_result(item) for item in items][:count]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise WebSearchUnavailable("Web search failed.") from exc


def is_deepseek_model(spec: str) -> bool:
    """Whether a ``provider:model`` spec runs on DeepSeek.

    Args:
        spec: Agent model spec.

    Returns:
        True for ``deepseek:*`` and the DeepSeek models served through the
        Anthropic-compatible endpoint.
    """
    provider, _, model_id = spec.partition(":")
    return provider == "deepseek" or (
        provider == "anthropic" and model_id.startswith("deepseek")
    )


def build_web_search(
    model_spec: str,
    model_api_key: str,
    exa_api_key: str | None = None,
) -> WebSearch | None:
    """Choose the search provider from the model and the available keys.

    A DeepSeek model searches through DeepSeek using the same model key.
    Every other model uses Exa when its key is configured.

    Args:
        model_spec: Agent ``provider:model`` spec.
        model_api_key: Key for the agent model.
        exa_api_key: Exa key, when present.

    Returns:
        A searcher, or ``None`` when nothing is configured.
    """
    if is_deepseek_model(model_spec) and model_api_key:
        return DeepSeekWebSearch(model_api_key)
    if exa_api_key:
        return ExaWebSearch(exa_api_key)
    return None


def _deepseek_result(item: Any) -> WebResult:
    summary = item.get("summary") or item.get("snippet") or ""
    authority = item.get("authority")
    return WebResult(
        title=str(item.get("title", "")),
        url=str(item.get("url", "")),
        summary=str(summary),
        published_at=item.get("date"),
        source="deepseek_search",
        authority=authority if isinstance(authority, int) else None,
    )


def _exa_result(item: Any) -> WebResult:
    highlights = item.get("highlights")
    summary = ""
    if isinstance(highlights, list) and highlights:
        summary = str(highlights[0])
    return WebResult(
        title=str(item.get("title", "")),
        url=str(item.get("url", "")),
        summary=summary,
        published_at=item.get("publishedDate"),
        source="exa_search",
    )
