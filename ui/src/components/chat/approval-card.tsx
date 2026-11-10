import { useState } from "react";
import { ShieldAlertIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ToolPartView } from "@/lib/parts";

/** Props for the approval card. */
export interface ApprovalCardProps {
  /** Tool part carrying the ticket descriptor. */
  view: ToolPartView;
  /** Sends the decision to the chat. */
  onRespond: (id: string, approved: boolean, reason?: string) => void;
}

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
 * Renders a ticket awaiting approval, or its execution result.
 *
 * @param props - Tool view and decision callback.
 * @returns The approval card.
 */
export function ApprovalCard({ view, onRespond }: ApprovalCardProps) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const approval = view.approval;
  const descriptor = approval?.descriptor ?? null;
  const ticket = descriptor?.ticket;
  const impact = descriptor?.portfolio_impact;
  const approvalId = approval?.id ?? view.toolCallId;
  const rejected = approval?.approved === false;
  const pendingExecution = approval?.approved === true && view.result === undefined;
  const hasResult = view.result !== undefined || rejected;
  const rationale =
    typeof descriptor?.rationale === "string" ? descriptor.rationale : ticket?.thesis;

  if (pendingExecution) {
    return (
      <div className="rounded-xl border bg-card px-4 py-3 text-sm">
        <p className="font-medium">Approval sent</p>
        <p className="mt-1 text-xs text-muted-foreground">Waiting for execution...</p>
      </div>
    );
  }

  if (hasResult) {
    const errorText = view.result?.errorText;
    const label = rejected
      ? "Ticket rejected"
      : errorText
        ? "Ticket failed"
        : "Ticket executed";
    return (
      <div className="rounded-xl border bg-card px-4 py-3 text-sm">
        <p className="font-medium">{label}</p>
        {approval?.reason ? (
          <p className="mt-1 text-xs text-muted-foreground">{approval.reason}</p>
        ) : null}
        {errorText ? (
          <p className="mt-1 text-xs" style={{ color: "var(--negative)" }}>
            {errorText}
          </p>
        ) : null}
      </div>
    );
  }

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

  return (
    <div className="overflow-hidden rounded-xl border border-primary/25 bg-card shadow-sm">
      <div className="flex items-center gap-2 border-b border-primary/20 bg-primary/5 px-4 py-2.5">
        <ShieldAlertIcon className="size-4 text-primary" />
        <span className="text-sm font-medium text-primary">
          Ticket requires your approval
        </span>
      </div>

      <div className="space-y-3 px-4 py-3">
        {ticket?.legs && ticket.legs.length > 0 ? (
          <ul className="space-y-1.5">
            {ticket.legs.map((leg) => (
              <li
                key={`${leg.ticker}-${leg.side}`}
                className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm"
              >
                <Badge variant="secondary" className="uppercase">
                  {leg.side}
                </Badge>
                <span className="font-mono font-semibold">{leg.ticker}</span>
                <span className="text-xs text-muted-foreground">{leg.qty} shares</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">The ticket has no legs.</p>
        )}

        {rationale ? (
          <p className="text-xs leading-relaxed text-muted-foreground">{rationale}</p>
        ) : null}

        {impact?.after_pct ? (
          <div className="space-y-1">
            <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Position weight
            </p>
            {Object.entries(impact.after_pct).map(([ticker, after]) => (
              <div key={ticker} className="flex items-center justify-between text-xs">
                <span className="font-mono">{ticker}</span>
                <span className="font-mono text-muted-foreground">
                  {weight(impact.before_pct?.[ticker])} to {weight(after)}
                </span>
              </div>
            ))}
          </div>
        ) : null}

        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>Net notional {usd(impact?.net_notional)}</span>
          <span>Equity {usd(impact?.equity)}</span>
        </div>

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
