import { useEffect, useState } from "react";
import { ChevronDownIcon, ChevronUpIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { listJournal, type JournalEntry, type JournalStatus } from "@/lib/api";
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
  ...STATUSES.map((status) => ({ value: status, label: status })),
];

const PAGE_SIZE = 20;

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
      <DialogContent className="max-h-[85vh] w-[min(960px,100vw-32px)] max-w-none overflow-y-auto sm:max-w-none">
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
          <Input
            aria-label="From date"
            type="date"
            value={filters.from ?? ""}
            onChange={(event) => setFilters({ ...filters, from: event.target.value })}
          />
          <Input
            aria-label="To date"
            type="date"
            value={filters.to ?? ""}
            onChange={(event) => setFilters({ ...filters, to: event.target.value })}
          />
        </div>

        {loading && entries.length === 0 ? <Skeleton className="h-40 w-full" /> : null}
        {error ? <p className="text-sm text-muted-foreground">{error}</p> : null}
        {!loading && !error && entries.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No decisions match these filters.
          </p>
        ) : null}

        <div className="space-y-2">
          {entries.map((entry) => {
            const isOpen = expanded === entry.id;
            return (
              <div key={entry.id} className="rounded-lg border">
                <button
                  type="button"
                  className="flex w-full items-start gap-3 px-3 py-2 text-left"
                  onClick={() => setExpanded(isOpen ? null : entry.id)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] text-muted-foreground">
                        {new Date(entry.created_at).toLocaleDateString()}
                      </span>
                      {entry.legs.map((leg) => (
                        <span
                          key={`${leg.ticker}-${leg.side}`}
                          className="font-mono text-xs"
                        >
                          {leg.ticker} {leg.side} {leg.qty}
                        </span>
                      ))}
                      <Badge variant="secondary">{entry.status}</Badge>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {entry.thesis}
                    </p>
                    <p className="mt-1 text-[11px] font-medium">
                      {outcomeLabel(entry.outcome)}
                    </p>
                  </div>
                  {isOpen ? (
                    <ChevronUpIcon className="size-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
                  )}
                </button>

                {isOpen ? (
                  <div className="space-y-1 border-t px-3 py-2 text-xs">
                    {entry.legs.map((leg) => (
                      <div
                        key={`${leg.ticker}-${leg.side}`}
                        className="flex gap-3 font-mono"
                      >
                        <span className="w-16">{leg.ticker}</span>
                        <span className="w-10">{leg.side}</span>
                        <span className="w-14">{leg.qty}</span>
                        <span className="w-24">{leg.notional.toFixed(2)}</span>
                        <span className="text-muted-foreground">
                          {leg.fill_price !== null
                            ? `fill ${leg.fill_price}`
                            : leg.status}
                        </span>
                      </div>
                    ))}
                    {entry.rejection_reason ? (
                      <p className="text-muted-foreground">
                        Reason: {entry.rejection_reason}
                      </p>
                    ) : null}
                    <p className="text-muted-foreground">
                      Horizon: {entry.horizon} · Action: {entry.user_action ?? "pending"}
                    </p>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>

        {entries.length < total ? (
          <div className="flex justify-center">
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
      </DialogContent>
    </Dialog>
  );
}
