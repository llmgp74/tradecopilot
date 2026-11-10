import type { KeyboardEvent } from "react";
import {
  BriefcaseIcon,
  ChevronsLeftIcon,
  NotebookTextIcon,
  PlusIcon,
  SettingsIcon,
  UserIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { groupThreads } from "@/lib/conversation";
import { isMacDesktop } from "@/lib/platform";
import type { ThreadSummary } from "@/lib/api";

/** Destinations that open as dialogs. */
export type DialogName = "portfolio" | "profile" | "journal" | "settings";

/** Props for the navigation rail. */
export interface RailProps {
  /** True when the expanded panel is visible. */
  open: boolean;
  /** Thread history, newest first. */
  threads: ThreadSummary[];
  /** Highlighted thread. */
  activeThreadId: string | null;
  /** Toggles between the rail and the panel. */
  onToggle: () => void;
  /** Starts a new conversation. */
  onNewChat: () => void;
  /** Opens a stored conversation. */
  onOpenThread: (threadId: string) => void;
  /** Opens one of the dialog destinations. */
  onOpenDialog: (name: DialogName) => void;
}

/** Destinations listed below the thread history. */
const DESTINATIONS: {
  name: Exclude<DialogName, "settings">;
  label: string;
  icon: typeof BriefcaseIcon;
}[] = [
  { name: "portfolio", label: "Portfolio", icon: BriefcaseIcon },
  { name: "profile", label: "Profile", icon: UserIcon },
  { name: "journal", label: "Journal", icon: NotebookTextIcon },
];

/**
 * Renders the expanded panel or the narrow icon rail.
 *
 * @param props - Thread history and callbacks.
 * @returns The rail.
 */
export function Rail({
  open,
  threads,
  activeThreadId,
  onToggle,
  onNewChat,
  onOpenThread,
  onOpenDialog,
}: RailProps) {
  const groups = groupThreads(threads, new Date());

  const handleListKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
      return;
    }
    const buttons = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>("[data-thread]"),
    );
    if (buttons.length === 0) {
      return;
    }
    event.preventDefault();
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      event.key === "ArrowDown"
        ? Math.min(current + 1, buttons.length - 1)
        : Math.max(current - 1, 0);
    buttons[Math.max(next, 0)]?.focus();
  };

  if (!open) {
    return (
      <aside
        aria-label="Navigation"
        className="flex h-full w-13 shrink-0 flex-col items-center gap-1 border-r bg-sidebar py-3"
      >
        {isMacDesktop() ? (
          <div data-tauri-drag-region className="h-8 w-full shrink-0" />
        ) : null}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Expand navigation"
          onClick={onToggle}
          className="mb-2"
        >
          <img src="/logo.svg" alt="TradeCopilot" className="size-6" />
        </Button>
        <Button variant="ghost" size="icon" aria-label="New chat" onClick={onNewChat}>
          <PlusIcon className="size-4" />
        </Button>
        {DESTINATIONS.map(({ name, label, icon: Icon }) => (
          <Button
            key={name}
            variant="ghost"
            size="icon"
            aria-label={label}
            onClick={() => onOpenDialog(name)}
          >
            <Icon className="size-4" />
          </Button>
        ))}
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="icon"
          aria-label="Settings"
          onClick={() => onOpenDialog("settings")}
        >
          <SettingsIcon className="size-4" />
        </Button>
      </aside>
    );
  }

  return (
    <>
      <div
        className="fixed inset-0 z-30 bg-foreground/20 lg:hidden"
        onClick={onToggle}
        aria-hidden
      />
      <aside
        aria-label="Navigation"
        className="fixed inset-y-0 left-0 z-40 flex h-full w-[clamp(232px,20vw,280px)] shrink-0 flex-col border-r bg-sidebar p-2 lg:static lg:z-auto"
      >
        {isMacDesktop() ? (
          <div data-tauri-drag-region className="h-8 w-full shrink-0" />
        ) : null}
        <div className="flex items-center gap-2 px-1 pb-3">
          <img src="/logo.svg" alt="TradeCopilot" className="size-7" />
          <span className="text-sm font-semibold">TradeCopilot</span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Collapse navigation"
            className="ml-auto"
            onClick={onToggle}
          >
            <ChevronsLeftIcon className="size-4" />
          </Button>
        </div>

        <Button
          variant="outline"
          className="mb-3 justify-start gap-2"
          onClick={onNewChat}
        >
          <PlusIcon className="size-3.5" />
          New chat
          <kbd className="ml-auto rounded border px-1 text-[10px] text-muted-foreground">
            Cmd N
          </kbd>
        </Button>

        <div
          role="listbox"
          aria-label="Conversations"
          className="min-h-0 flex-1 overflow-y-auto"
          onKeyDown={handleListKeys}
        >
          {groups.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">
              No conversations yet.
            </p>
          ) : (
            groups.map((group) => (
              <div key={group.label} className="mb-2">
                <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {group.label}
                </p>
                {group.items.map((thread) => (
                  <button
                    key={thread.thread_id}
                    data-thread
                    type="button"
                    role="option"
                    aria-selected={thread.thread_id === activeThreadId}
                    onClick={() => onOpenThread(thread.thread_id)}
                    className="block w-full truncate rounded-md px-2 py-1.5 text-left text-xs text-foreground hover:bg-accent aria-selected:bg-accent aria-selected:font-medium"
                  >
                    {thread.title}
                  </button>
                ))}
              </div>
            ))
          )}
        </div>

        <div className="flex flex-col gap-0.5 border-t pt-2">
          {DESTINATIONS.map(({ name, label, icon: Icon }) => (
            <Button
              key={name}
              variant="ghost"
              size="sm"
              className="justify-start gap-2"
              onClick={() => onOpenDialog(name)}
            >
              <Icon className="size-4 text-muted-foreground" />
              {label}
            </Button>
          ))}
          <Button
            variant="ghost"
            size="sm"
            className="justify-start gap-2"
            onClick={() => onOpenDialog("settings")}
          >
            <SettingsIcon className="size-4 text-muted-foreground" />
            Settings
          </Button>
        </div>
      </aside>
    </>
  );
}
