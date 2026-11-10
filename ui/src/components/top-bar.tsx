import { MinusIcon, PanelLeftIcon, SquareIcon, XIcon } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Button } from "@/components/ui/button";
import { isMacDesktop, isWindowsDesktop } from "@/lib/platform";

/** Props for the top bar. */
export interface TopBarProps {
  /** Current conversation title. */
  title: string;
  /** Toggles the navigation rail. */
  onToggleRail: () => void;
  /** True when the expanded navigation rail is visible. */
  railOpen: boolean;
}

/**
 * Renders the conversation header and the Windows window controls.
 *
 * @param props - Title, rail callback and rail state.
 * @returns The top bar.
 */
export function TopBar({ title, onToggleRail, railOpen }: TopBarProps) {
  const window = () => getCurrentWindow();

  return (
    <header
      data-tauri-drag-region
      className="flex h-12 shrink-0 items-center gap-2 border-b px-3"
    >
      {isMacDesktop() && !railOpen ? <div className="w-5 shrink-0" /> : null}
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Toggle navigation"
        onClick={onToggleRail}
      >
        <PanelLeftIcon className="size-4" />
      </Button>
      <span className="truncate text-sm font-medium">{title}</span>
      {isWindowsDesktop() ? (
        <div className="ml-auto flex items-center">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Minimize"
            onClick={() => void window().minimize()}
          >
            <MinusIcon className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Maximize"
            onClick={() => void window().toggleMaximize()}
          >
            <SquareIcon className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Close"
            onClick={() => void window().close()}
          >
            <XIcon className="size-4" />
          </Button>
        </div>
      ) : null}
    </header>
  );
}
