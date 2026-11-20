import { useState } from "react";
import { CheckCircle2Icon, ShieldAlertIcon, XCircleIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import type { ToolPartView } from "@/lib/parts";

/** Props for the approval card. */
export interface ApprovalCardProps {
  /** Tool part carrying the ticket descriptor. */
  view: ToolPartView;
  /** Sends the decision to the chat. */
  onRespond: (id: string, approved: boolean, reason?: string) => void;
  /** Error that stopped the approved ticket from executing. */
  failure?: string | null;
}

/** One ticket leg, from the descriptor, the execution result, or both. */
interface TicketLeg {
  ticker?: string;
  side?: string;
  qty?: number;
  status?: string;
  fill_price?: number | null;
  entry_price?: number | null;
  order_type?: string;
}

/** Parsed execution result carried in the tool output. */
interface ExecutionResult {
  status?: string;
  legs?: TicketLeg[];
}

const LEG_STATUS_LABELS: Record<string, string> = {
  filled: "Filled",
  failed: "Failed",
  skipped_unfunded: "Skipped, unfunded",
};

const TICKET_STATUS_LABELS: Record<string, string> = {
  filled: "Executed",
  submitted: "Submitted",
  failed: "Failed",
};

/** Formats a weight in percentage points. */
function weight(value: number | undefined): string {
  return value === undefined ? "-" : `${value.toFixed(2)}%`;
}

/** Formats US dollars without cents for impact totals. */
function usd(value: number | undefined): string {
  if (value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

/**
 * Formats the order price a reader is approving.
 *
 * A market order shows the quote it was built from with a tilde, because the
 * fill can differ. A limit order shows its fixed limit.
 *
 * @param leg - Ticket leg with a price.
 * @returns The formatted price, or "-" when none was recorded.
 */
function legPrice(leg: TicketLeg): string {
  if (leg.entry_price === null || leg.entry_price === undefined) {
    return "-";
  }
  const shown = price(leg.entry_price);
  return leg.order_type === "limit" ? shown : `~${shown}`;
}

/** Formats a share price with two decimals. */
function price(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/** Preview rows before the full list moves into a dialog. */
const PREVIEW_ROWS = 10;

/**
 * Formats the portfolio weight before and after one leg.
 *
 * @param before - Weight before the trade, when known.
 * @param after - Weight after the trade, when known.
 * @returns Both weights, or a dash without impact data.
 */
function weightChange(before?: number, after?: number): string {
  if (before === undefined && after === undefined) {
    return "-";
  }
  return `${weight(before)} to ${weight(after)}`;
}

/** Props for the leg table. */
interface TicketTableProps {
  /** Legs to render. */
  legs: TicketLeg[];
  /** Portfolio impact keyed by ticker. */
  impact?: TicketBodyProps["impact"];
}

/**
 * Renders one compact row per order.
 *
 * @param props - Legs and impact weights.
 * @returns The table.
 */
function TicketTable({ legs, impact }: TicketTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full table-fixed text-xs">
        <thead>
          <tr className="border-b text-[10px] uppercase tracking-wide text-muted-foreground">
            <th className="w-[14%] px-3 py-1.5 text-left font-medium">Symbol</th>
            <th className="w-[10%] px-3 py-1.5 text-left font-medium">Side</th>
            <th className="w-[8%] px-3 py-1.5 text-right font-medium">Size</th>
            <th className="w-[12%] px-3 py-1.5 text-left font-medium">Type</th>
            <th className="w-[18%] px-3 py-1.5 text-right font-medium">Price</th>
            <th className="w-[38%] px-3 py-1.5 text-right font-medium">Weight change</th>
          </tr>
        </thead>
        <tbody>
          {legs.map((leg, index) => {
            const detail =
              typeof leg.fill_price === "number"
                ? `Filled at ${price(leg.fill_price)}`
                : (LEG_STATUS_LABELS[leg.status ?? ""] ?? null);
            return (
              <tr
                key={`${leg.ticker}-${leg.side}-${index}`}
                className="border-b last:border-0"
              >
                <td className="px-3 py-1.5">
                  <span className="font-mono font-semibold">{leg.ticker ?? "?"}</span>
                  {detail ? (
                    <span className="block text-[10px] text-muted-foreground">
                      {detail}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-1.5">
                  <span className="text-[10px] font-medium uppercase text-muted-foreground">
                    {leg.side ?? "?"}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                  {leg.qty ?? 0}
                </td>
                <td className="px-3 py-1.5">
                  <span className="text-[10px] font-medium uppercase text-muted-foreground">
                    {leg.order_type ?? "market"}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                  {legPrice(leg)}
                </td>
                <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                  {weightChange(
                    leg.ticker ? impact?.before_pct?.[leg.ticker] : undefined,
                    leg.ticker ? impact?.after_pct?.[leg.ticker] : undefined,
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Reads the execution legs and status from a tool output.
 *
 * The output is the tool summary, a JSON string optionally followed by an
 * evidence line.
 *
 * @param output - Tool output, string or already-parsed object.
 * @returns The parsed result, or null when it is not a ticket result.
 */
function parseExecution(output: unknown): ExecutionResult | null {
  let value: unknown = output;
  if (typeof value === "string") {
    const text = value.split("\nEvidence:")[0]?.trim() ?? "";
    try {
      value = JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  return {
    status: typeof record.status === "string" ? record.status : undefined,
    legs: Array.isArray(record.legs) ? (record.legs as TicketLeg[]) : undefined,
  };
}

/**
 * Merges the ticket legs with the execution legs, which carry fills.
 *
 * @param ticketLegs - Legs from the approval descriptor.
 * @param resultLegs - Legs from the execution result.
 * @returns One leg per order, execution fields winning when present.
 */
function mergedLegs(
  ticketLegs: TicketLeg[],
  resultLegs: TicketLeg[] | undefined,
): TicketLeg[] {
  if (!resultLegs || resultLegs.length === 0) {
    return ticketLegs;
  }
  return resultLegs.map((leg, index) => ({ ...ticketLegs[index], ...leg }));
}

/** Props for the shared ticket body. */
interface TicketBodyProps {
  /** Legs to list. */
  legs: TicketLeg[];
  /** Ticket thesis or draft recommendation. */
  rationale?: string;
  /** Portfolio impact from the descriptor. */
  impact?: {
    before_pct?: Record<string, number>;
    after_pct?: Record<string, number>;
    net_notional?: number;
    equity?: number;
  } | null;
}

/**
 * Lists the ticket legs and the context around them.
 *
 * More than ten legs are previewed; the full list opens in a dialog.
 *
 * @param props - Legs, rationale, and portfolio impact.
 * @returns The ticket body.
 */
function TicketBody({ legs, rationale, impact }: TicketBodyProps) {
  const [showAll, setShowAll] = useState(false);
  return (
    <div className="space-y-3 py-3">
      {legs.length > 0 ? (
        <TicketTable legs={legs.slice(0, PREVIEW_ROWS)} impact={impact} />
      ) : (
        <p className="px-4 text-sm text-muted-foreground">The ticket has no legs.</p>
      )}

      {legs.length > PREVIEW_ROWS ? (
        <div className="px-4">
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto px-0"
            onClick={() => setShowAll(true)}
          >
            Show all {legs.length} legs
          </Button>
        </div>
      ) : null}

      {rationale ? (
        <p className="px-4 text-xs leading-relaxed text-muted-foreground">{rationale}</p>
      ) : null}

      {impact ? (
        <div className="flex items-center gap-3 px-4 text-xs text-muted-foreground">
          <span>Net notional {usd(impact.net_notional)}</span>
          <span>Equity {usd(impact.equity)}</span>
        </div>
      ) : null}

      <Dialog open={showAll} onOpenChange={setShowAll}>
        <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Ticket legs</DialogTitle>
            <DialogDescription>{legs.length} orders in this ticket.</DialogDescription>
          </DialogHeader>
          <TicketTable legs={legs} impact={impact} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Renders a ticket awaiting approval, or its resolved state after a decision.
 *
 * Once a decision is made the actions are gone and the card keeps the legs,
 * the fills, and the outcome.
 *
 * @param props - Tool view and decision callback.
 * @returns The approval card.
 */
export function ApprovalCard({ view, onRespond, failure }: ApprovalCardProps) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const approval = view.approval;
  const descriptor = approval?.descriptor ?? null;
  const ticket = descriptor?.ticket;
  const impact = descriptor?.portfolio_impact;
  const approvalId = approval?.id ?? view.toolCallId;
  const rejected = approval?.approved === false;
  const pendingExecution = approval?.approved === true && view.result === undefined;
  const resolved = view.result !== undefined || rejected;
  const rationale =
    typeof descriptor?.rationale === "string" ? descriptor.rationale : ticket?.thesis;

  if (descriptor?.error && !ticket) {
    return (
      <div
        className="rounded-xl border px-4 py-3 text-sm"
        style={{ color: "var(--negative)" }}
      >
        {descriptor.error}
      </div>
    );
  }

  if (resolved) {
    const execution = rejected ? null : parseExecution(view.result?.output);
    const legs = mergedLegs(ticket?.legs ?? [], execution?.legs);
    const failure = view.result?.errorText;
    const title = rejected
      ? "Ticket rejected"
      : (TICKET_STATUS_LABELS[execution?.status ?? ""] ??
        (failure ? "Failed" : "Ticket executed"));

    return (
      <div className="overflow-hidden rounded-xl border bg-card text-sm">
        <div className="flex items-center gap-2 border-b px-4 py-2.5">
          {rejected || failure ? (
            <XCircleIcon className="size-4" style={{ color: "var(--negative)" }} />
          ) : (
            <CheckCircle2Icon className="size-4" />
          )}
          <span className="font-medium">{title}</span>
          {execution?.status ? (
            <Badge variant="secondary" className="ml-auto uppercase">
              {execution.status}
            </Badge>
          ) : null}
        </div>
        <TicketBody legs={legs} rationale={rationale} impact={impact} />
        {approval?.reason ? (
          <p className="px-4 pb-3 text-xs text-muted-foreground">
            Reason: {approval.reason}
          </p>
        ) : null}
        {failure ? (
          <p className="px-4 pb-3 text-xs" style={{ color: "var(--negative)" }}>
            {failure}
          </p>
        ) : null}
      </div>
    );
  }

  if (pendingExecution) {
    return (
      <div className="overflow-hidden rounded-xl border bg-card text-sm">
        <div className="flex items-center gap-2 border-b px-4 py-2.5">
          {failure ? (
            <XCircleIcon className="size-4" style={{ color: "var(--negative)" }} />
          ) : (
            <ShieldAlertIcon className="size-4 text-muted-foreground" />
          )}
          <span className="font-medium">
            {failure ? "Execution did not start" : "Approval sent"}
          </span>
          {failure ? null : (
            <span className="ml-auto text-xs text-muted-foreground">
              Waiting for execution...
            </span>
          )}
        </div>
        <TicketBody legs={ticket?.legs ?? []} rationale={rationale} impact={impact} />
        {failure ? (
          <div className="space-y-2 px-4 pb-3">
            <p className="text-xs" style={{ color: "var(--negative)" }}>
              {failure}
            </p>
            <Button size="sm" onClick={() => onRespond(approvalId, true)}>
              Retry approval
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-primary/25 bg-card shadow-sm">
      <div className="flex items-center gap-2 border-b border-primary/20 bg-primary/5 px-4 py-2.5">
        <ShieldAlertIcon className="size-4 text-primary" />
        <span className="text-sm font-medium">Ticket requires your approval</span>
      </div>

      <TicketBody legs={ticket?.legs ?? []} rationale={rationale} impact={impact} />

      <div className="space-y-2 px-4 pb-3">
        {rejecting ? (
          <div className="space-y-2">
            <label htmlFor={`reason-${approvalId}`} className="text-xs font-medium">
              Reason
            </label>
            <Textarea
              id={`reason-${approvalId}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Optional context for the journal..."
              rows={2}
            />
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  onRespond(approvalId, false, reason.trim() || undefined);
                  setRejecting(false);
                }}
              >
                Confirm rejection
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setRejecting(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => onRespond(approvalId, true)}>
              Approve ticket
            </Button>
            <Button variant="outline" size="sm" onClick={() => setRejecting(true)}>
              Reject
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
