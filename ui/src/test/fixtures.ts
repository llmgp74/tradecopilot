import type { AppSettings, Profile } from "@/lib/api";

/** Profile fixture with non-empty values so diff tests can clear fields. */
export const baseProfile: Profile = {
  risk_band: "moderate",
  position_cap_pct: 10,
  sector_exclusions: ["Energy"],
  horizon: "weeks",
  watchlist: ["MSFT"],
  source_preferences: ["sec_edgar", "finnhub"],
  execution: { autonomous: false, max_order_notional: 1000 },
  updated_at: "2026-11-01T00:00:00Z",
};

/** Settings fixture with non-empty values so diff tests can clear fields. */
export const baseSettings: AppSettings = {
  agent_model: "deepseek:deepseek-flash",
  model_api_key: "sk-model",
  alpaca_api_key: "PK-alpaca",
  alpaca_api_secret: "secret-alpaca",
  alpaca_base_url: "https://paper-api.alpaca.markets",
  fmp_api_key: "fmp-key",
  finnhub_api_key: "finnhub-key",
  fred_api_key: "fred-key",
  edgar_user_agent: "TradeCopilot test@example.com",
  exa_api_key: "exa-key",
  updated_at: "2026-11-01T00:00:00Z",
};
