import { PanelLeftIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Props for the top bar. */
export interface TopBarProps {
  /** Current conversation title. */
  title: string;
  /** Toggles the navigation rail. */
  onToggleRail: () => void;
}

/**
 * Renders the conversation header.
 *
 * @param props - Title and rail callback.
 * @returns The top bar.
 */
export function TopBar({ title, onToggleRail }: TopBarProps) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Toggle navigation"
        onClick={onToggleRail}
      >
        <PanelLeftIcon className="size-4" />
      </Button>
      <span className="truncate text-sm font-medium">{title}</span>
    </header>
  );
}
