import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ToolPartView } from "@/lib/parts";

/** Props for the in-row approval controls. */
export interface ToolApprovalActionsProps {
  /** Tool part waiting for a decision. */
  view: ToolPartView;
  /** Sends the decision to the chat. */
  onRespond: (id: string, approved: boolean, reason?: string) => void;
}

/**
 * Renders approve and reject controls for a gated tool call.
 *
 * @param props - Pending call and the decision callback.
 * @returns The action row.
 */
export function ToolApprovalActions({ view, onRespond }: ToolApprovalActionsProps) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const approvalId = view.approval?.id ?? view.toolCallId;

  return (
    <div className="space-y-2 border-t px-2 py-2">
      {rejecting ? (
        <div className="space-y-2">
          <label htmlFor={`tool-reason-${approvalId}`} className="text-xs font-medium">
            Reason
          </label>
          <Textarea
            id={`tool-reason-${approvalId}`}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Optional context for the model..."
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
            Approve
          </Button>
          <Button variant="outline" size="sm" onClick={() => setRejecting(true)}>
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}
