import type { AppSettings } from "./api";

/** Broker connection state shown in the top bar. */
export type BrokerState = "unconfigured" | "saved" | "connected" | "error";

/** Portfolio probe outcome. */
export type BrokerProbe = "ok" | "unconfigured" | "error" | "pending";

/** Display status derived from settings and the probe. */
export interface ConnectionStatus {
  broker: BrokerState;
  environment: "paper" | "live" | null;
  environmentVerified: boolean;
}

/**
 * Derives the top bar status.
 *
 * A successful probe is the only thing that marks the connection verified. The
 * environment falls back to the saved base URL until then, so a saved Live URL
 * never looks confirmed.
 *
 * @param settings - Effective settings.
 * @param probe - Portfolio call outcome.
 * @param paper - The probe's paper flag, when it succeeded.
 * @returns The display status.
 */
export function deriveConnectionStatus(
  settings: AppSettings,
  probe: BrokerProbe,
  paper: boolean | null,
): ConnectionStatus {
  const hasKeys =
    (settings.alpaca_api_key ?? "") !== "" && (settings.alpaca_api_secret ?? "") !== "";
  const baseUrl = settings.alpaca_base_url ?? "";
  const fromUrl =
    baseUrl === ""
      ? null
      : baseUrl.includes("paper-api")
        ? ("paper" as const)
        : ("live" as const);
  if (!hasKeys) {
    return {
      broker: "unconfigured",
      environment: null,
      environmentVerified: false,
    };
  }
  if (probe === "ok" && paper !== null) {
    return {
      broker: "connected",
      environment: paper ? "paper" : "live",
      environmentVerified: true,
    };
  }
  return {
    broker: probe === "error" ? "error" : "saved",
    environment: fromUrl,
    environmentVerified: false,
  };
}
