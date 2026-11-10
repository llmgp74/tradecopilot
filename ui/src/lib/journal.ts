import type { JournalOutcome, JournalQuery, JournalStatus } from "./api";
import { formatSignedPct } from "./format";

/** Journal filter fields owned by the dialog. */
export interface JournalFilters {
  status?: JournalStatus;
  ticker?: string;
  from?: string;
  to?: string;
}

/**
 * Builds an API query from the dialog filters.
 *
 * @param filters - Raw filter values.
 * @returns The query with empty strings and undefined values removed.
 */
export function journalQuery(filters: JournalFilters): JournalQuery {
  const query: JournalQuery = {};
  if (filters.status) {
    query.status = filters.status;
  }
  const ticker = filters.ticker?.trim();
  if (ticker) {
    query.ticker = ticker;
  }
  if (filters.from) {
    query.from = filters.from;
  }
  if (filters.to) {
    query.to = filters.to;
  }
  return query;
}

/**
 * Summarizes a decision outcome.
 *
 * @param outcome - Computed outcome, or null while pending.
 * @returns A short alpha label.
 */
export function outcomeLabel(outcome: JournalOutcome | null): string {
  if (outcome === null) {
    return "Pending";
  }
  const prefix = outcome.counterfactual ? "Counterfactual " : "";
  return `${prefix}${formatSignedPct(outcome.alpha_pct)} alpha`;
}
