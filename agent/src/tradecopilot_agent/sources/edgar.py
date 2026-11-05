"""SEC EDGAR filings and XBRL facts. Free, no key, contact header required."""

from collections.abc import Callable
from typing import Any, cast

import httpx

from tradecopilot_agent.models import AppSettings
from tradecopilot_agent.sources.common import record
from tradecopilot_agent.sources.http import fetch_json
from tradecopilot_agent.state import ToolOutput

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"


class EdgarSource:
    """EDGAR adapter with a cached ticker to CIK map."""

    def __init__(
        self,
        settings: Callable[[], AppSettings],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Bind the adapter to the effective settings.

        Args:
            settings: Callable returning the current settings.
            client: Injected HTTP client for tests.
        """
        self.settings = settings
        self.client = client
        self._ciks: dict[str, str] | None = None

    def capabilities(self) -> set[str]:
        """Return EDGAR when a contact header is configured."""
        if self.settings().edgar_user_agent.strip():
            return {"edgar"}
        return set()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.settings().edgar_user_agent,
            "Accept-Encoding": "gzip, deflate",
        }

    async def _cik(self, ticker: str) -> str | None:
        if self._ciks is None:
            data = await fetch_json(
                TICKERS_URL, headers=self._headers(), client=self.client
            )
            self._ciks = (
                {
                    str(item["ticker"]).upper(): str(item["cik_str"]).zfill(10)
                    for item in data.values()
                }
                if isinstance(data, dict)
                else {}
            )
        return self._ciks.get(ticker)

    async def filings(self, ticker: str, limit: int = 10) -> ToolOutput:
        """Return recent filings."""
        try:
            cik = await self._cik(ticker)
            if cik is None:
                return ToolOutput(summary=f"No CIK for {ticker}.", error="missing")
            data = await fetch_json(
                SUBMISSIONS_URL.format(cik=cik),
                headers=self._headers(),
                client=self.client,
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            return ToolOutput(summary=f"EDGAR filings failed: {exc}", error="http")
        recent = (data.get("filings") or {}).get("recent") or {}
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        dates = recent.get("filingDate") or []
        records = []
        for index in range(min(limit, len(forms))):
            payload = {
                "kind": "filing",
                "ticker": ticker,
                "filing_type": forms[index],
                "accession": accessions[index],
                "date": dates[index],
            }
            records.append(
                record(
                    "get_filings",
                    {"ticker": ticker, "limit": limit},
                    "sec_edgar",
                    payload,
                    url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                    f"{accessions[index].replace('-', '')}",
                    published_at=dates[index],
                )
            )
        return ToolOutput(
            summary=f"{len(records)} filings for {ticker}", evidence=records
        )

    async def xbrl_fact(
        self, ticker: str, tag: str, period: str, unit: str
    ) -> ToolOutput:
        """Return one XBRL fact."""
        try:
            cik = await self._cik(ticker)
            if cik is None:
                return ToolOutput(summary=f"No CIK for {ticker}.", error="missing")
            data = await fetch_json(
                CONCEPT_URL.format(cik=cik, tag=tag),
                headers=self._headers(),
                client=self.client,
            )
        except (httpx.HTTPError, ValueError) as exc:
            return ToolOutput(summary=f"EDGAR fact failed: {exc}", error="http")
        entries: list[dict[str, Any]] = (data.get("units") or {}).get(unit) or []
        if not entries:
            return ToolOutput(summary=f"No {unit} facts for {tag}.", error="missing")
        chosen = _pick(entries, period)
        if chosen is None:
            return ToolOutput(summary="No fact for that period.", error="missing")
        payload = {
            "kind": "xbrl",
            "ticker": ticker,
            "tag": tag,
            "period": chosen.get("end"),
            "fiscal_period": f"FY{chosen.get('fy')}Q{chosen.get('fp')}"
            if chosen.get("fy")
            else None,
            "unit": unit,
            "value": chosen.get("val"),
            "form": chosen.get("form"),
        }
        return ToolOutput(
            summary=f"{ticker} {tag} {chosen.get('end')}: {chosen.get('val')} {unit}",
            evidence=[
                record(
                    "get_xbrl_fact",
                    {"ticker": ticker, "tag": tag, "period": period, "unit": unit},
                    "sec_edgar",
                    payload,
                    published_at=chosen.get("filed"),
                )
            ],
        )


def _pick(entries: list[dict[str, Any]], period: str) -> dict[str, Any] | None:
    if period.upper().startswith("FY"):
        for entry in reversed(entries):
            if f"FY{entry.get('fy')}Q{entry.get('fp')}".upper() == period.upper():
                return cast("dict[str, Any]", entry)
    for entry in reversed(entries):
        if str(entry.get("end")) == period:
            return cast("dict[str, Any]", entry)
    return entries[-1] if entries else None
