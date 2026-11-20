"use client";

import { camelName } from "@/components/chat/tool-label";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  CheckCircleIcon,
  ChevronDownIcon,
  CircleIcon,
  ClockIcon,
  WrenchIcon,
  XCircleIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { CodeBlock } from "./code-block";

/** Optional controlled open state, used when a row outlives its shape. */
interface OpenControl {
  /** Controlled open state. */
  open?: boolean;
  /** Called when the user toggles the row. */
  onOpenChange?: (open: boolean) => void;
}

/** One tool call reduced to what a compact row and its panel render. */
export interface ToolCallProps {
  /** One-line row text derived from the purpose or the arguments. */
  label: string;
  /** Raw tool name, shown in camelCase inside the panel. */
  name: string;
  /** AI SDK tool state. */
  state: string;
  /** Call arguments. */
  input?: unknown;
  /** Tool result. */
  output?: unknown;
  /** Failure text, when the call errored. */
  errorText?: string;
  /** Extra controls rendered under the parameters and result panel. */
  actions?: ReactNode;
}

/** Row status presentation. */
interface StatusTone {
  label: string;
  color: string;
  icon: ReactNode;
}

/**
 * Maps a tool state to its row label, color, and icon.
 *
 * @param state - AI SDK tool state.
 * @returns The status presentation.
 */
function statusOf(state: string): StatusTone {
  switch (state) {
    case "output-available":
      return {
        label: "Completed",
        color: "var(--positive)",
        icon: <CheckCircleIcon className="size-4" />,
      };
    case "output-error":
    case "output-denied":
      return {
        label: "Failed",
        color: "var(--negative)",
        icon: <XCircleIcon className="size-4" />,
      };
    case "approval-requested":
      return {
        label: "Awaiting approval",
        color: "var(--warning)",
        icon: <ClockIcon className="size-4" />,
      };
    case "input-available":
    case "approval-responded":
      return {
        label: "Running",
        color: "var(--muted-foreground)",
        icon: <CircleIcon className="size-3.5 animate-pulse" />,
      };
    default:
      return {
        label: "Pending",
        color: "var(--muted-foreground)",
        icon: <CircleIcon className="size-4" />,
      };
  }
}

/**
 * Aggregates the states of a tool group.
 *
 * @param states - Member call states.
 * @returns Running while any call runs, else Failed, else Completed.
 */
export function aggregateState(states: string[]): string {
  const running = new Set([
    "input-available",
    "input-streaming",
    "approval-requested",
    "approval-responded",
  ]);
  if (states.some((state) => running.has(state))) {
    return "input-available";
  }
  if (states.some((state) => state === "output-error" || state === "output-denied")) {
    return "output-error";
  }
  return "output-available";
}

/**
 * Renders the shared row trigger for one call or one group.
 *
 * @param props - Row props.
 * @returns The collapsible row.
 */
function ToolRow({
  label,
  state,
  open,
  onOpenChange,
  children,
}: {
  label: string;
  state: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  const status = statusOf(state);
  return (
    <Collapsible open={open} onOpenChange={onOpenChange} className="group w-full">
      <CollapsibleTrigger className="group/chev -mx-2 flex min-h-8 w-full min-w-0 items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors hover:bg-muted/40">
        <WrenchIcon className="size-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 wrap-break-word">{label}</span>
        <span
          className="flex shrink-0 items-center"
          style={{ color: status.color }}
          title={status.label}
          aria-label={status.label}
        >
          {status.icon}
        </span>
        <span className="flex-1" />
        <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[panel-open]/chev:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}

/**
 * Copies the call arguments without the row label argument.
 *
 * The purpose exists for the row text; showing it as a parameter only adds
 * noise to the panel.
 *
 * @param input - Raw tool arguments.
 * @returns The arguments without `purpose`, or the value unchanged when it is
 *   not an object.
 */
function parametersOf(input: unknown): unknown {
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    return input;
  }
  const parameters = { ...(input as Record<string, unknown>) };
  delete parameters.purpose;
  return parameters;
}

/**
 * Renders parameters and the result in a fixed-width two-column panel.
 *
 * Every block keeps `min-width: 0`, so wide content scrolls inside its own
 * box instead of widening the message column.
 *
 * @param props - Panel props.
 * @returns The detail panel.
 */
function ToolPanel({
  name,
  input,
  output,
  errorText,
}: {
  name: string;
  input?: unknown;
  output?: unknown;
  errorText?: string;
}) {
  const parameters = input === undefined ? {} : parametersOf(input);
  const text = typeof output === "string" ? output : null;
  return (
    <div className="grid w-full min-w-0 gap-3 border-t px-2 py-2 sm:grid-cols-2">
      <div className="min-w-0">
        <div className="mb-1 flex items-baseline gap-2">
          <h4 className="font-medium text-[10px] text-muted-foreground uppercase tracking-wide">
            Parameters
          </h4>
          <span className="text-[10px] text-muted-foreground/70">{camelName(name)}</span>
        </div>
        <div className="max-h-48 min-w-0 overflow-auto rounded-md bg-muted/40 text-xs">
          <CodeBlock code={JSON.stringify(parameters, null, 2)} language="json" />
        </div>
      </div>
      <div className="min-w-0">
        <h4 className="mb-1 font-medium text-[10px] text-muted-foreground uppercase tracking-wide">
          {errorText ? "Error" : "Result"}
        </h4>
        {errorText ? (
          <p className="text-xs" style={{ color: "var(--negative)" }}>
            {errorText}
          </p>
        ) : (
          <div className="max-h-64 min-w-0 overflow-auto rounded-md bg-muted/40 text-xs">
            {text !== null ? (
              <pre className="whitespace-pre-wrap wrap-break-word p-2">{text}</pre>
            ) : output === undefined ? null : (
              <CodeBlock code={JSON.stringify(output, null, 2)} language="json" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Renders one tool call as a compact row that opens on demand.
 *
 * The row starts closed. It opens itself once when the call starts waiting
 * for approval; after that the user controls it, and later state changes never
 * reopen or close it.
 *
 * @param props - Call props.
 * @returns The row and its panel.
 */
export function ToolCall({
  label,
  name,
  state,
  input,
  output,
  errorText,
  actions,
  open: controlledOpen,
  onOpenChange,
}: ToolCallProps & OpenControl) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  // A call waiting for a decision opens itself so the command is visible.
  // The user can collapse it afterwards; the state does not change again.
  useEffect(() => {
    if (state === "approval-requested" && controlledOpen === undefined) {
      setInternalOpen(true);
    }
  }, [state, controlledOpen]);

  return (
    <ToolRow label={label} state={state} open={open} onOpenChange={setOpen}>
      <ToolPanel name={name} input={input} output={output} errorText={errorText} />
      {actions}
    </ToolRow>
  );
}

/**
 * Renders the group row and its child calls.
 *
 * @param props - Group props.
 * @returns The group row and the child rows inside its panel.
 */
export function ToolGroup({
  label,
  state,
  children,
  open: controlledOpen,
  onOpenChange,
}: {
  label: string;
  state: string;
  children: ReactNode;
} & OpenControl) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  return (
    <ToolRow label={label} state={state} open={open} onOpenChange={setOpen}>
      <div className="flex min-w-0 flex-col border-t py-1 pl-4">{children}</div>
    </ToolRow>
  );
}
