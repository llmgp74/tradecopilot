import type { UIMessage } from "ai";

/** One leg of an order ticket. */
export interface TicketLeg {
  ticker: string;
  side: "buy" | "sell";
  qty: number;
}

/** Order ticket carried by the approval descriptor. */
export interface Ticket {
  id?: string;
  legs?: TicketLeg[];
  thesis?: string;
  horizon?: string;
  created_at?: string;
}

/** Portfolio impact of a proposed ticket. */
export interface PortfolioImpact {
  before_pct?: Record<string, number>;
  after_pct?: Record<string, number>;
  net_notional?: number;
  equity?: number;
}

/** Payload rendered by the approval card. */
export interface ApprovalDescriptor {
  ticket?: Ticket;
  rationale?: unknown;
  portfolio_impact?: PortfolioImpact | null;
  error?: string;
}

/** Approval metadata on a tool part. */
export interface ApprovalView {
  id: string;
  approved?: boolean;
  reason?: string;
  descriptor: ApprovalDescriptor | null;
}

/** A tool call reduced to what the UI renders. */
export interface ToolPartView {
  kind: "tool";
  toolCallId: string;
  name: string;
  state: string;
  input?: unknown;
  output?: unknown;
  errorText?: string;
  approval?: ApprovalView;
  result?: { output?: unknown; errorText?: string };
  hidden?: boolean;
}

/** One item of the agent plan. */
export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

export type DisplayPart =
  | { kind: "text"; text: string }
  | { kind: "reasoning"; text: string; streaming: boolean }
  | ToolPartView
  | { kind: "data"; name: string; data: unknown };

/** One message reduced from the live or rehydrated wire shape. */
export interface DisplayMessage {
  id: string;
  role: string;
  parts: DisplayPart[];
  todos: TodoItem[] | null;
}

type RawPart = Record<string, unknown> & { type?: string };

/**
 * Returns the tool name for a dynamic or static tool part.
 *
 * @param part - Raw UI message part.
 * @returns The tool name, or null when the part is not a tool call.
 */
export function toolNameOf(part: { type?: string; toolName?: string }): string | null {
  if (part.type === "dynamic-tool") {
    return typeof part.toolName === "string" ? part.toolName : null;
  }
  if (typeof part.type === "string" && part.type.startsWith("tool-")) {
    return part.type.slice("tool-".length);
  }
  return null;
}

/**
 * Builds the approval view from either wire shape.
 *
 * @param raw - Raw `approval` object.
 * @returns The normalized approval, or null.
 */
function toApprovalView(raw: unknown): ApprovalView | null {
  if (raw === null || typeof raw !== "object") {
    return null;
  }
  const approval = raw as Record<string, unknown>;
  const id = approval.id;
  if (typeof id !== "string" || !id) {
    return null;
  }
  const nested = approval.descriptor;
  let descriptor: ApprovalDescriptor | null;
  if (nested !== null && typeof nested === "object") {
    descriptor = nested as ApprovalDescriptor;
  } else {
    const flatKeys = ["ticket", "rationale", "portfolio_impact", "error"] as const;
    const flat: Record<string, unknown> = {};
    for (const key of flatKeys) {
      if (key in approval) {
        flat[key] = approval[key];
      }
    }
    descriptor = Object.keys(flat).length > 0 ? (flat as ApprovalDescriptor) : null;
  }
  return {
    id,
    approved: typeof approval.approved === "boolean" ? approval.approved : undefined,
    reason: typeof approval.reason === "string" ? approval.reason : undefined,
    descriptor,
  };
}

/**
 * Converts one raw part to a display part.
 *
 * @param raw - Raw UI message part.
 * @param firstToolParts - Map of tool call id to the first rendered card.
 * @returns The display part, or null for parts the UI ignores.
 */
function toDisplayPart(
  raw: RawPart,
  firstToolParts: Map<string, ToolPartView>,
): DisplayPart | null {
  if (raw.type === "text" && typeof raw.text === "string") {
    return { kind: "text", text: raw.text };
  }
  if (raw.type === "reasoning" && typeof raw.text === "string") {
    return {
      kind: "reasoning",
      text: raw.text,
      streaming: raw.state === "streaming",
    };
  }
  if (raw.type === "data-verification" || raw.type === "data-todos") {
    return null;
  }

  const name = toolNameOf({ type: raw.type, toolName: raw.toolName as string });
  if (name !== null) {
    const toolCallId = typeof raw.toolCallId === "string" ? raw.toolCallId : "";
    const view: ToolPartView = {
      kind: "tool",
      toolCallId,
      name,
      state: typeof raw.state === "string" ? raw.state : "input-available",
      input: raw.input,
      output: raw.output,
      errorText: typeof raw.errorText === "string" ? raw.errorText : undefined,
      approval: toApprovalView(raw.approval) ?? undefined,
    };
    const earlier = firstToolParts.get(toolCallId);
    if (earlier !== undefined) {
      const finished = raw.state === "output-available" || raw.state === "output-error";
      if (finished) {
        earlier.result = { output: raw.output, errorText: view.errorText };
        earlier.state = String(raw.state);
      }
      view.hidden = true;
    } else {
      firstToolParts.set(toolCallId, view);
    }
    return view;
  }

  if (typeof raw.type === "string") {
    return { kind: "data", name: raw.type, data: raw.data };
  }
  return null;
}

/**
 * Reduces live and rehydrated messages to one display shape.
 *
 * Later copies of the same tool call are folded into the first card, so an
 * executed ticket renders once.
 *
 * @param messages - UI messages from `useChat` or thread detail.
 * @returns Display messages ready for rendering.
 */
export function normalizeMessages(messages: UIMessage[]): DisplayMessage[] {
  const firstToolParts = new Map<string, ToolPartView>();
  return messages.map((message) => {
    const parts: DisplayPart[] = [];
    let todos: TodoItem[] | null = null;

    const rawParts = (message.parts ?? []) as unknown as RawPart[];
    for (const raw of rawParts) {
      if (raw.type === "data-verification") {
        continue;
      }
      if (raw.type === "data-todos") {
        const items = (raw.data as { todos?: TodoItem[] } | undefined)?.todos;
        if (Array.isArray(items)) {
          todos = items;
        }
        continue;
      }
      const part = toDisplayPart(raw, firstToolParts);
      if (part !== null) {
        parts.push(part);
      }
    }

    return {
      id: message.id,
      role: message.role,
      parts,
      todos,
    };
  });
}
