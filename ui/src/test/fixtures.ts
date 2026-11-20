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
  suggestions: [],
};

/** Settings fixture with non-empty values so diff tests can clear fields. */
export const baseSettings: AppSettings = {
  model_provider: "deepseek",
  model_id: "deepseek-flash",
  reasoning_effort: "",
  alpaca_api_key: "PK-alpaca",
  alpaca_api_secret: "secret-alpaca",
  alpaca_base_url: "https://paper-api.alpaca.markets",
  fmp_api_key: "fmp-key",
  finnhub_api_key: "finnhub-key",
  fred_api_key: "fred-key",
  edgar_user_agent: "TradeCopilot test@example.com",
  exa_api_key: "exa-key",
  tool_permissions: {
    execute: "ask",
    write_file: "auto",
    edit_file: "auto",
    delete: "auto",
  },
  providers: [
    {
      provider_id: "deepseek",
      api_key: "sk-model",
      base_url: "",
      npm: "@ai-sdk/openai-compatible",
      models: [
        {
          id: "deepseek-flash",
          name: "DeepSeek V4.1 Flash",
          tool_call: true,
          reasoning_options: [
            { type: "toggle" },
            { type: "effort", values: ["low", "high", "max"] },
          ],
        },
      ],
      updated_at: "2026-11-01T00:00:00Z",
    },
  ],
  updated_at: "2026-11-01T00:00:00Z",
};
