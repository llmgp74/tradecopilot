import { useState } from "react";
import type { ReactNode } from "react";
import { MessageResponse } from "@/components/ai-elements/message";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task, TaskContent, TaskItem, TaskTrigger } from "@/components/ai-elements/task";
import { ToolCall, ToolGroup, aggregateState } from "@/components/ai-elements/tool";
import type { DisplayMessage, TodoItem, ToolPartView } from "@/lib/parts";
import { ApprovalCard } from "./approval-card";
import { groupLabel, rowLabel } from "./tool-label";

/**
 * Labels a reasoning block with the actual streamed duration.
 *
 * @param streaming - Whether the block is still streaming.
 * @param duration - Elapsed seconds, when known.
 * @returns The trigger text.
 */
function thinkingLabel(streaming: boolean, duration?: number) {
  if (streaming || duration === 0) {
    return <Shimmer duration={1}>Thinking...</Shimmer>;
  }
  if (duration === undefined) {
    return <p>Thought for a few seconds</p>;
  }
  return (
    <p>
      Thought for {duration} second{duration === 1 ? "" : "s"}
    </p>
  );
}

/**
 * Returns whether a tool part needs the ticket approval card.
 *
 * @param view - Normalized tool part.
 * @returns True for an execution call awaiting or carrying a decision.
 */
function needsApproval(view: ToolPartView): boolean {
  return (
    view.name === "execute_ticket" &&
    (view.state === "approval-requested" ||
      view.approval?.approved !== undefined ||
      (view.result !== undefined && view.approval !== undefined))
  );
}

/**
 * Reads the model-written purpose from the call arguments.
 *
 * @param view - Normalized tool part.
 * @returns The purpose, or undefined when absent or not a string.
 */
function purposeOf(view: ToolPartView): string | undefined {
  if (view.input === null || typeof view.input !== "object") {
    return undefined;
  }
  const purpose = (view.input as Record<string, unknown>).purpose;
  return typeof purpose === "string" ? purpose : undefined;
}

/** Props for one assistant message body. */
export interface AssistantPartsProps {
  /** Normalized message. */
  message: DisplayMessage;
  /** Plan from the live stream, which is transient on the wire. */
  liveTodos?: TodoItem[] | null;
  /** True while this message is the turn still being generated. */
  isStreaming?: boolean;
  /** Answered tool calls, where the caller needs the raw ids. */
  onApproval: (id: string, approved: boolean, reason?: string) => void;
}

/**
 * Renders one tool call with its row label and detail panel.
 *
 * @param view - Normalized tool part.
 * @returns The call row.
 */
function ToolCallRow({ view }: { view: ToolPartView }) {
  return (
    <ToolCall
      label={rowLabel(view.name, view.input, purposeOf(view))}
      name={view.name}
      state={view.state}
      input={view.input}
      output={view.output}
      errorText={view.errorText}
    />
  );
}

/**
 * Renders one row for a run of consecutive calls to the same tool.
 *
 * @param run - Tool parts in wire order, all with the same name.
 * @returns The group row or, for a single call, a plain call row.
 */
function ToolRun({ run }: { run: ToolPartView[] }) {
  // Held here, keyed by the run's first call, so a row the user opened stays
  // open when a second call turns it into a group.
  const [open, setOpen] = useState(false);
  const first = run[0];
  if (run.length === 1) {
    return (
      <ToolCall
        label={rowLabel(first.name, first.input, purposeOf(first))}
        name={first.name}
        state={first.state}
        input={first.input}
        output={first.output}
        errorText={first.errorText}
        open={open}
        onOpenChange={setOpen}
      />
    );
  }
  return (
    <ToolGroup
      label={groupLabel(
        first.name,
        run.map((view) => view.input),
      )}
      state={aggregateState(run.map((view) => view.state))}
      open={open}
      onOpenChange={setOpen}
    >
      {run.map((view, index) => (
        <ToolCallRow key={view.toolCallId || `call-${index}`} view={view} />
      ))}
    </ToolGroup>
  );
}

/**
 * Renders the reasoning, plan, tool calls, and answer for one assistant turn.
 *
 * @param props - Message and live overrides.
 * @returns The message body.
 */
export function AssistantParts({
  message,
  liveTodos,
  isStreaming,
  onApproval,
}: AssistantPartsProps) {
  const todos = liveTodos ?? message.todos;
  const visibleParts = message.parts.filter(
    (part) => part.kind !== "tool" || !part.hidden,
  );

  const rendered: ReactNode[] = [];
  let index = 0;
  while (index < visibleParts.length) {
    const part = visibleParts[index];
    if (part.kind === "tool") {
      if (needsApproval(part)) {
        rendered.push(
          <ApprovalCard
            key={part.toolCallId || `approval-${index}`}
            view={part}
            onRespond={onApproval}
          />,
        );
        index += 1;
        continue;
      }
      let end = index + 1;
      while (end < visibleParts.length) {
        const next = visibleParts[end];
        if (next.kind !== "tool" || next.name !== part.name || needsApproval(next)) {
          break;
        }
        end += 1;
      }
      rendered.push(
        <ToolRun
          key={part.toolCallId || `run-${index}`}
          run={visibleParts.slice(index, end) as ToolPartView[]}
        />,
      );
      index = end;
      continue;
    }
    if (part.kind === "reasoning") {
      rendered.push(
        <Reasoning
          key={`reasoning-${index}`}
          isStreaming={part.streaming && isStreaming === true}
          autoOpen={false}
        >
          <ReasoningTrigger getThinkingMessage={thinkingLabel} />
          <ReasoningContent>{part.text}</ReasoningContent>
        </Reasoning>,
      );
    } else if (part.kind === "text") {
      rendered.push(<MessageResponse key={`text-${index}`}>{part.text}</MessageResponse>);
    }
    index += 1;
  }

  return (
    <div className="flex w-full flex-col gap-2">
      {todos && todos.length > 0 ? (
        <Task defaultOpen>
          <TaskTrigger title="Plan" />
          <TaskContent>
            {todos.map((todo) => (
              <TaskItem
                key={todo.content}
                className="flex items-center justify-between gap-2"
              >
                <span>{todo.content}</span>
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {todo.status.replace("_", " ")}
                </span>
              </TaskItem>
            ))}
          </TaskContent>
        </Task>
      ) : null}

      {rendered}
    </div>
  );
}
