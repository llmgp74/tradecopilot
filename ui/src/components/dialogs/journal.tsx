import { useEffect, useState } from "react";
import { CalendarIcon, ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import type { DateRange } from "react-day-picker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  listJournal,
  type JournalEntry,
  type JournalLeg,
  type JournalStatus,
} from "@/lib/api";
import { formatSignedPct, formatUsd } from "@/lib/format";
import { journalQuery, outcomeLabel, type JournalFilters } from "@/lib/journal";
import type { DialogProps } from "./portfolio";

const STATUSES: JournalStatus[] = [
  "proposed",
  "approved",
  "edited",
  "rejected",
  "deferred",
  "submitted",
  "filled",
  "failed",
  "skipped_unfunded",
];

const STATUS_ITEMS = [
  { value: "all", label: "All statuses" },
  ...STATUSES.map((status) => ({ value: status, label: humanize(status) })),
];

const PAGE_SIZE = 20;
const SUMMARY_TICKERS = 3;

/**
 * Color tone per journal status.
 *
 * Outcomes read first: approved and filled are positive, rejected and failed
 * are negative, deferred and edited await a decision. Everything else stays
 * neutral so the list does not turn into a traffic light.
 */
const STATUS_TONES: Partial<Record<JournalStatus, "positive" | "negative" | "warning">> =
  {
    approved: "positive",
    edited: "warning",
    rejected: "negative",
    deferred: "warning",
    submitted: "warning",
    filled: "positive",
    failed: "negative",
    skipped_unfunded: "negative",
  };

/**
 * Renders a journal status with its color tone.
 *
 * @param props.status - Journal-level status.
 * @returns A badge tinted by the status tone.
 */
function StatusBadge({ status }: { status: JournalStatus }) {
  const tone = STATUS_TONES[status];
  if (tone === undefined) {
    return <Badge variant="secondary">{humanize(status)}</Badge>;
  }
  const color = `var(--${tone})`;
  return (
    <Badge
      variant="outline"
      className="border-0"
      style={{
        color,
        background: `color-mix(in oklch, ${color} 15%, transparent)`,
      }}
    >
      {humanize(status)}
    </Badge>
  );
}

/**
 * Turns an enum value into readable words.
 *
 * @param value - Status value such as `skipped_unfunded`.
 * @returns The value with underscores replaced and the first letter capitalized.
 */
function humanize(value: string): string {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Builds the one-line summary shown before a decision is expanded.
 *
 * A single leg reads as an order. Several legs read as a count and the first
 * few tickers, which keeps twenty-leg baskets to one line.
 *
 * @param legs - The decision's legs.
 * @returns A short summary.
 */
function decisionSummary(legs: JournalLeg[]): string {
  if (legs.length === 0) {
    return "No legs";
  }
  if (legs.length === 1) {
    const [leg] = legs;
    const quantity = Number.isInteger(leg.qty) ? leg.qty : leg.qty.toFixed(2);
    return `${leg.ticker} ${leg.side} ${quantity}`;
  }
  const tickers = [...new Set(legs.map((leg) => leg.ticker))];
  const shown = tickers.slice(0, SUMMARY_TICKERS).join(", ");
  const more = tickers.length - SUMMARY_TICKERS;
  return `${legs.length} legs: ${shown}${more > 0 ? ` +${more}` : ""}`;
}

/**
 * Parses an `yyyy-mm-dd` filter value as a local calendar day.
 *
 * @param value - Stored filter value.
 * @returns The day, or undefined when the value is empty or malformed.
 */
function parseDay(value: string | undefined): Date | undefined {
  if (!value) {
    return undefined;
  }
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) {
    return undefined;
  }
  return new Date(year, month - 1, day);
}

/**
 * Formats a day as `yyyy-mm-dd` without a time zone shift.
 *
 * @param date - Calendar day.
 * @returns The filter value.
 */
function isoDay(date: Date): string {
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * Renders a calendar day for the trigger label.
 *
 * @param date - Calendar day.
 * @returns A short label such as "Nov 19".
 */
function formatDay(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

/**
 * Describes the selected day range.
 *
 * @param from - Lower bound, when set.
 * @param to - Upper bound, when set.
 * @returns A short label for the date trigger.
 */
function rangeLabel(from: Date | undefined, to: Date | undefined): string {
  if (!from && !to) {
    return "Any date";
  }
  if (from && to) {
    return isoDay(from) === isoDay(to)
      ? formatDay(from)
      : `${formatDay(from)} - ${formatDay(to)}`;
  }
  return from ? `From ${formatDay(from)}` : `Until ${formatDay(to as Date)}`;
}

/**
 * Journal destination dialog.
 *
 * @param props - Open state.
 * @returns The dialog.
 */
export function JournalDialog({ open, onOpenChange }: DialogProps) {
  const [filters, setFilters] = useState<JournalFilters>({});
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dateOpen, setDateOpen] = useState(false);
  const fromDay = parseDay(filters.from);
  const toDay = parseDay(filters.to);
  const selectedRange: DateRange | undefined =
    fromDay || toDay ? { from: fromDay, to: toDay } : undefined;

  useEffect(() => {
    if (!open) {
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    listJournal({ ...journalQuery(filters), pageNo: 1, pageSize: PAGE_SIZE })
      .then((response) => {
        if (active) {
          setEntries(response.items);
          setTotal(response.total);
          setPage(1);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : "Request failed.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [open, filters]);

  const loadMore = async () => {
    setLoading(true);
    try {
      const next = page + 1;
      const response = await listJournal({
        ...journalQuery(filters),
        pageNo: next,
        pageSize: PAGE_SIZE,
      });
      setEntries((current) => [...current, ...response.items]);
      setPage(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] w-[min(960px,100vw-32px)] max-w-none flex-col overflow-hidden sm:max-w-none">
        <DialogHeader>
          <DialogTitle>Journal</DialogTitle>
          <DialogDescription>Past decisions and their outcomes.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Select
            items={STATUS_ITEMS}
            value={filters.status ?? "all"}
            onValueChange={(value) =>
              setFilters({
                ...filters,
                status: value === "all" ? undefined : (value as JournalStatus),
              })
            }
          >
            <SelectTrigger aria-label="Status" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_ITEMS.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            aria-label="Ticker"
            placeholder="Ticker"
            value={filters.ticker ?? ""}
            onChange={(event) => setFilters({ ...filters, ticker: event.target.value })}
          />
          <Popover open={dateOpen} onOpenChange={setDateOpen}>
            <PopoverTrigger
              render={
                <Button
                  variant="outline"
                  aria-label="Date range"
                  className="col-span-2 w-full justify-start gap-2 font-normal"
                />
              }
            >
              <CalendarIcon className="size-4 text-muted-foreground" />
              {rangeLabel(fromDay, toDay)}
            </PopoverTrigger>
            <PopoverContent align="start" className="w-auto p-0">
              <Calendar
                mode="range"
                selected={selectedRange}
                onSelect={(range) =>
                  setFilters({
                    ...filters,
                    from: range?.from ? isoDay(range.from) : undefined,
                    to: range?.to ? isoDay(range.to) : undefined,
                  })
                }
              />
              <div className="flex justify-end border-t p-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setFilters({ ...filters, from: undefined, to: undefined });
                    setDateOpen(false);
                  }}
                >
                  Clear dates
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
          {loading && entries.length === 0 ? <Skeleton className="h-40 w-full" /> : null}
          {error ? <p className="text-sm text-muted-foreground">{error}</p> : null}
          {!loading && !error && entries.length === 0 ? (
            <p className="flex flex-1 items-center justify-center py-10 text-center text-sm text-muted-foreground">
              No decisions match these filters.
            </p>
          ) : null}

          <div className="shrink-0 divide-y divide-border overflow-hidden rounded-lg border">
            {entries.map((entry) => {
              const isOpen = expanded === entry.id;
              const detailsId = `${entry.id}-details`;
              const hasFill = entry.legs.some((leg) => leg.fill_price !== null);
              const legStatuses = new Set(entry.legs.map((leg) => leg.status));
              const sharedStatus =
                !hasFill && legStatuses.size === 1 ? [...legStatuses][0] : null;
              return (
                <article key={entry.id}>
                  <button
                    type="button"
                    aria-expanded={isOpen}
                    aria-controls={detailsId}
                    className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-accent/40"
                    onClick={() => setExpanded(isOpen ? null : entry.id)}
                  >
                    <div className="min-w-0">
                      <div className="flex min-w-0 items-center gap-2">
                        <StatusBadge status={entry.status} />
                        <span className="truncate text-xs font-medium">
                          {decisionSummary(entry.legs)}
                        </span>
                      </div>
                      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {entry.thesis}
                      </p>
                      {entry.outcome ? (
                        <p className="mt-1 text-[11px] tabular-nums text-muted-foreground">
                          {outcomeLabel(entry.outcome)}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-2 pt-0.5">
                      <time
                        dateTime={entry.created_at}
                        className="text-[11px] tabular-nums text-muted-foreground"
                      >
                        {new Date(entry.created_at).toLocaleDateString()}
                      </time>
                      {isOpen ? (
                        <ChevronUpIcon className="size-4 text-muted-foreground" />
                      ) : (
                        <ChevronDownIcon className="size-4 text-muted-foreground" />
                      )}
                    </div>
                  </button>

                  {isOpen ? (
                    <div id={detailsId} className="border-t px-3 py-2.5">
                      <div className="max-h-72 overflow-auto">
                        <table className="w-full min-w-100 text-xs">
                          <thead className="sticky top-0 bg-popover">
                            <tr className="text-[11px] text-muted-foreground">
                              <th className="pb-1 pr-3 text-left font-medium">Ticker</th>
                              <th className="pb-1 pr-3 text-left font-medium">Side</th>
                              <th className="pb-1 pr-3 text-right font-medium">Qty</th>
                              <th className="pb-1 pr-3 text-right font-medium">
                                Notional
                              </th>
                              {hasFill ? (
                                <th className="pb-1 text-left font-medium">Fill</th>
                              ) : null}
                            </tr>
                          </thead>
                          <tbody className="tabular-nums">
                            {entry.legs.map((leg) => (
                              <tr key={`${leg.ticker}-${leg.side}`}>
                                <td className="py-0.5 pr-3 font-mono">{leg.ticker}</td>
                                <td className="py-0.5 pr-3">{leg.side}</td>
                                <td className="py-0.5 pr-3 text-right">{leg.qty}</td>
                                <td className="py-0.5 pr-3 text-right">
                                  {formatUsd(leg.notional, 0)}
                                </td>
                                {hasFill ? (
                                  <td className="py-0.5 text-muted-foreground">
                                    {leg.fill_price !== null
                                      ? formatUsd(leg.fill_price)
                                      : humanize(leg.status)}
                                  </td>
                                ) : null}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>

                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                        <span>Horizon: {entry.horizon}</span>
                        {sharedStatus ? (
                          <span>Order: {humanize(sharedStatus)}</span>
                        ) : null}
                        <span>Action: {entry.user_action ?? "pending"}</span>
                        <span>
                          {entry.evidence_ids.length}{" "}
                          {entry.evidence_ids.length === 1 ? "source" : "sources"}
                        </span>
                      </div>

                      {entry.rejection_reason ? (
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          Reason: {entry.rejection_reason}
                        </p>
                      ) : null}

                      {entry.outcome ? (
                        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] tabular-nums sm:grid-cols-4">
                          <div>
                            <dt className="text-muted-foreground">Return</dt>
                            <dd>{formatSignedPct(entry.outcome.return_pct)}</dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">Alpha</dt>
                            <dd>
                              {entry.outcome.alpha_pct !== null
                                ? formatSignedPct(entry.outcome.alpha_pct)
                                : "n/a"}
                            </dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">Observed</dt>
                            <dd>{entry.outcome.observed_at ?? "unknown"}</dd>
                          </div>
                          <div>
                            <dt className="text-muted-foreground">Entry</dt>
                            <dd>{formatUsd(entry.outcome.entry_price)}</dd>
                          </div>
                        </dl>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>

          {entries.length < total ? (
            <div className="flex shrink-0 justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void loadMore()}
                disabled={loading}
              >
                Load more
              </Button>
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
