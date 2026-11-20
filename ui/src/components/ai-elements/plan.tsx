import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { TodoItem } from "@/lib/parts";
import { cn } from "@/lib/utils";
import {
  ChevronDownIcon,
  CircleCheckIcon,
  CircleDotIcon,
  CircleIcon,
  ListChecksIcon,
} from "lucide-react";
import type { ComponentProps } from "react";

/**
 * Icon, label, and colour for each plan step status.
 *
 * The visible icon carries no text, so the label goes into a screen-reader
 * span beside the step content and the icon itself is hidden from assistive
 * technology.
 */
const STATUS = {
  completed: {
    icon: CircleCheckIcon,
    label: "Done",
    className: "text-muted-foreground",
  },
  in_progress: {
    icon: CircleDotIcon,
    label: "In progress",
    className: "animate-pulse text-foreground",
  },
  pending: {
    icon: CircleIcon,
    label: "Pending",
    className: "text-muted-foreground/60",
  },
} as const;

/** Props for the plan card. */
export type PlanProps = Omit<ComponentProps<typeof Collapsible>, "children"> & {
  /** Steps in the order the agent will take them. */
  todos: TodoItem[];
};

/**
 * Shows the agent's plan with a completion count and per-step status.
 *
 * @param props - Plan props.
 * @returns The collapsible plan card.
 */
export function Plan({ todos, className, defaultOpen = true, ...props }: PlanProps) {
  const done = todos.filter((todo) => todo.status === "completed").length;
  return (
    <Collapsible
      defaultOpen={defaultOpen}
      className={cn("w-full rounded-lg border bg-muted/30", className)}
      {...props}
    >
      <CollapsibleTrigger className="group/chev flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors hover:bg-muted/40">
        <ListChecksIcon className="size-4 shrink-0 text-muted-foreground" />
        <span className="text-sm">Plan</span>
        <span className="flex-1" />
        <span className="text-muted-foreground text-xs tabular-nums">
          {done} of {todos.length} done
        </span>
        <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[panel-open]/chev:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="flex flex-col gap-1.5 px-3 pb-3">
          {todos.map((todo, index) => {
            const status = STATUS[todo.status];
            const Icon = status.icon;
            return (
              <li
                key={`${index}-${todo.content}`}
                className="flex items-start gap-2 text-sm"
              >
                <Icon
                  aria-hidden
                  className={cn("mt-0.5 size-4 shrink-0", status.className)}
                />
                <span
                  className={cn(
                    "min-w-0 wrap-break-word",
                    todo.status === "completed" &&
                      "text-muted-foreground line-through decoration-muted-foreground/50",
                  )}
                >
                  <span className="sr-only">{status.label}: </span>
                  {todo.content}
                </span>
              </li>
            );
          })}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
