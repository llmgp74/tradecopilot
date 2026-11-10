import type { UIMessage } from "ai";
import { apiUrl } from "./api-base";

/** Error raised for any non-2xx API response. */
export class ApiError extends Error {
  /** HTTP status code. */
  readonly status: number;

  /**
   * @param status - HTTP status code.
   * @param message - Server detail text.
   */
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface Health {
  status: string;
  agent_model: string;
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadList {
  items: ThreadSummary[];
  page_no: number;
  page_size: number;
  total: number;
}

export interface ThreadDetail extends ThreadSummary {
  messages: UIMessage[];
}

export type PortfolioRange = "1D" | "1W" | "1M" | "3M" | "1Y" | "ALL";

export interface Account {
  currency: string;
  equity: number;
  cash: number;
  buying_power: number;
  long_market_value: number;
}

export interface DayPnl {
  pnl: number;
  pnl_pct: number;
}

export interface Position {
  ticker: string;
  side: "long" | "short";
  sector: string | null;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  weight_pct: number;
}

export interface EquityPoint {
  t: string;
  equity: number;
}

export interface Portfolio {
  as_of: string;
  paper: boolean;
  account: Account;
  day: DayPnl;
  positions: Position[];
  equity_curve: EquityPoint[];
}

export type RiskBand = "conservative" | "moderate" | "aggressive";
export type Horizon = "intraday" | "days" | "weeks" | "months";

export interface ExecutionSettings {
  autonomous: boolean;
  max_order_notional: number;
}

export interface Profile {
  risk_band: RiskBand;
  position_cap_pct: number;
  sector_exclusions: string[];
  horizon: Horizon;
  watchlist: string[];
  source_preferences: string[];
  execution: ExecutionSettings;
  updated_at: string;
}

export type ProfilePatch = Partial<Omit<Profile, "updated_at">>;

export type JournalStatus =
  | "proposed"
  | "approved"
  | "edited"
  | "rejected"
  | "deferred"
  | "submitted"
  | "filled"
  | "failed"
  | "skipped_unfunded";

export type Side = "buy" | "sell";
export type UserAction = "approve" | "edit" | "reject" | "defer";

export interface JournalLeg {
  ticker: string;
  side: Side;
  qty: number;
  notional: number;
  fill_price: number | null;
  fill_at: string | null;
  status: JournalStatus;
}

export interface LegOutcome {
  ticker: string;
  entry_price: number;
  return_pct: number;
  alpha_pct: number;
  counterfactual: boolean;
}

export interface JournalOutcome {
  counterfactual: boolean;
  entry_price: number;
  entry_at: string;
  horizon: Horizon;
  return_pct: number;
  benchmark: string;
  benchmark_return_pct: number;
  alpha_pct: number;
  computed_at: string;
  legs: LegOutcome[];
}

export interface JournalEntry {
  id: string;
  created_at: string;
  legs: JournalLeg[];
  thesis: string;
  horizon: Horizon;
  evidence_ids: string[];
  status: JournalStatus;
  user_action: UserAction | null;
  rejection_reason: string | null;
  outcome: JournalOutcome | null;
}

export interface JournalList {
  items: JournalEntry[];
  page_no: number;
  page_size: number;
  total: number;
}

export interface JournalQuery {
  pageNo?: number;
  pageSize?: number;
  status?: JournalStatus;
  ticker?: string;
  from?: string;
  to?: string;
}

export interface AppSettings {
  agent_model: string;
  model_api_key: string;
  alpaca_api_key: string;
  alpaca_api_secret: string;
  alpaca_base_url: string;
  fmp_api_key: string;
  finnhub_api_key: string;
  fred_api_key: string;
  edgar_user_agent: string;
  exa_api_key: string;
  updated_at: string;
}

export type AppSettingsPatch = Partial<Omit<AppSettings, "updated_at">>;

/**
 * Calls one API endpoint and returns its parsed JSON body.
 *
 * @param path - Path beginning with `/api`.
 * @param init - Fetch options.
 * @returns The parsed payload.
 * @throws ApiError When the response status is not 2xx.
 */
async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), init);
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, detailText(payload));
  }
  return payload as T;
}

/**
 * Extracts a readable message from an error body.
 *
 * @param payload - Parsed response body.
 * @returns The detail string, first validation message, or a fallback.
 */
function detailText(payload: unknown): string {
  if (payload === null || typeof payload !== "object") {
    return "Request failed.";
  }
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first.msg === "string") {
      return first.msg;
    }
  }
  return "Request failed.";
}

/**
 * Builds a query string, omitting empty values.
 *
 * @param params - Parameter map.
 * @returns A query string beginning with `?`, or an empty string.
 */
function queryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") {
      continue;
    }
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** @returns Server readiness and the effective model string. */
export function getHealth(): Promise<Health> {
  return apiRequest<Health>("/api/health");
}

/**
 * Lists conversation threads.
 *
 * @param pageNo - One-based page.
 * @param pageSize - Rows per page.
 * @returns One page of thread metadata.
 */
export function listThreads(pageNo = 1, pageSize = 50): Promise<ThreadList> {
  return apiRequest<ThreadList>(
    `/api/threads${queryString({ page_no: pageNo, page_size: pageSize })}`,
  );
}

/**
 * Loads one thread with its messages.
 *
 * @param threadId - Thread identifier.
 * @returns Thread metadata and messages.
 */
export function getThread(threadId: string): Promise<ThreadDetail> {
  return apiRequest<ThreadDetail>(`/api/threads/${encodeURIComponent(threadId)}`);
}

/**
 * Loads the portfolio.
 *
 * @param range - Equity curve window.
 * @returns Account, positions, and history.
 */
export function getPortfolio(range: PortfolioRange): Promise<Portfolio> {
  return apiRequest<Portfolio>(`/api/portfolio${queryString({ range })}`);
}

/** @returns The effective user profile. */
export function getProfile(): Promise<Profile> {
  return apiRequest<Profile>("/api/profile");
}

/**
 * Applies a partial profile update.
 *
 * @param patch - Fields to change.
 * @returns The full profile after the update.
 */
export function patchProfile(patch: ProfilePatch): Promise<Profile> {
  return apiRequest<Profile>("/api/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

/**
 * Lists decision journal entries.
 *
 * @param query - Filters and pagination.
 * @returns One page of journal entries.
 */
export function listJournal(query: JournalQuery = {}): Promise<JournalList> {
  return apiRequest<JournalList>(
    `/api/journal${queryString({
      page_no: query.pageNo,
      page_size: query.pageSize,
      status: query.status,
      ticker: query.ticker,
      from: query.from,
      to: query.to,
    })}`,
  );
}

/** @returns The effective application settings. */
export function getSettings(): Promise<AppSettings> {
  return apiRequest<AppSettings>("/api/settings");
}

/**
 * Applies a partial settings update.
 *
 * @param patch - Fields to change.
 * @returns The full effective settings after the update.
 */
export function patchSettings(patch: AppSettingsPatch): Promise<AppSettings> {
  return apiRequest<AppSettings>("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}
