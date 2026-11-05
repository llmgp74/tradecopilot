"""One HTTP client shared by the provider adapters."""

import asyncio
from typing import Any

import httpx

RETRY_STATUS = {429, 503}


async def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """Fetch a JSON document, retrying once on throttling.

    Args:
        url: Absolute URL.
        headers: Request headers.
        params: Query parameters.
        client: Injected client, used by tests.

    Returns:
        The decoded response.

    Raises:
        httpx.HTTPError: When the request fails after the retry.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=15.0) as owned:
            return await _fetch(owned, url, headers, params)
    return await _fetch(client, url, headers, params)


async def post_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> Any:
    """Post a JSON body and return the decoded response.

    Args:
        url: Absolute URL.
        headers: Request headers.
        body: JSON body.
        client: Injected client, used by tests.

    Returns:
        The decoded response.

    Raises:
        httpx.HTTPError: When the request fails.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=15.0) as owned:
            response = await owned.post(url, headers=headers, json=body)
    else:
        response = await client.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()


async def _fetch(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str] | None,
    params: dict[str, Any] | None,
) -> Any:
    for attempt in range(2):
        response = await client.get(url, headers=headers, params=params)
        if response.status_code in RETRY_STATUS and attempt == 0:
            await asyncio.sleep(0.5)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("unreachable")
