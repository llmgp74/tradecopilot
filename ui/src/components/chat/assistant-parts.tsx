import { useEffect, useState } from "react";
import type { ToolUIPart } from "ai";
import { MessageResponse } from "@/components/ai-elements/message";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Task, TaskContent, TaskItem, TaskTrigger } from "@/components/ai-elements/task";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import type { DisplayMessage, TodoItem, ToolPartView } from "@/lib/parts";
import { ApprovalCard } from "./approval-card";
import { toolTitle } from "./tool-label";

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
 * Renders one tool call as a collapsible card.
 *
 * @param props - Tool view.
 * @param props.view - Normalized tool part.
 * @returns The tool card.
 */
function ToolCard({
  view,
  isStreaming,
  onApproval,
}: {
  view: ToolPartView;
  isStreaming?: boolean;
  onApproval: (id: string, approved: boolean, reason?: string) => void;
}) {
  const partFinished =
    view.state === "output-available" ||
    view.state === "output-error" ||
    view.state === "output-denied";
  // Some middleware tool calls never get a result. Folding on turn end keeps
  // those cards closed instead of stuck open.
  const settled = partFinished || isStreaming !== true;
  const [open, setOpen] = useState(!settled);
  useEffect(() => setOpen(!settled), [settled]);

  const needsApproval =
    view.name === "execute_ticket" &&
    (view.state === "approval-requested" ||
      view.approval?.approved !== undefined ||
      (view.result !== undefined && view.approval !== undefined));
  if (needsApproval) {
    return <ApprovalCard view={view} onRespond={onApproval} />;
  }

  return (
    <Tool open={open} onOpenChange={setOpen}>
      <ToolHeader
        title={toolTitle(view.name)}
        type="dynamic-tool"
        toolName={view.name}
        state={view.state as ToolUIPart["state"]}
      />
      <ToolContent>
        {view.input !== undefined ? <ToolInput input={view.input} /> : null}
        <ToolOutput output={view.output} errorText={view.errorText} />
      </ToolContent>
    </Tool>
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

      {visibleParts.map((part, index) => {
        if (part.kind === "reasoning") {
          return (
            <Reasoning
              key={`reasoning-${index}`}
              isStreaming={part.streaming && isStreaming === true}
            >
              <ReasoningTrigger getThinkingMessage={thinkingLabel} />
              <ReasoningContent>{part.text}</ReasoningContent>
            </Reasoning>
          );
        }
        if (part.kind === "tool") {
          return (
            <ToolCard
              key={part.toolCallId || `tool-${index}`}
              view={part}
              isStreaming={isStreaming}
              onApproval={onApproval}
            />
          );
        }
        if (part.kind === "text") {
          return <MessageResponse key={`text-${index}`}>{part.text}</MessageResponse>;
        }
        return null;
      })}
    </div>
  );
}
