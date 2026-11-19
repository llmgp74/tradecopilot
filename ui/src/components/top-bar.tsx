import { MinusIcon, PanelLeftIcon, SquareIcon, XIcon } from "lucide-react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ConnectionStatus } from "@/lib/connection";
import { isMacDesktop, isWindowsDesktop } from "@/lib/platform";

/** Props for the top bar. */
export interface TopBarProps {
  /** Current conversation title. */
  title: string;
  /** Toggles the navigation rail. */
  onToggleRail: () => void;
  /** True when the expanded navigation rail is visible. */
  railOpen: boolean;
  /** Broker and environment status. */
  status: ConnectionStatus;
  /** Opens Settings on the broker section. */
  onOpenSettings: (section: "broker") => void;
}

/**
 * Renders the conversation header and the Windows window controls.
 *
 * @param props - Title, rail callback and rail state.
 * @returns The top bar.
 */
export function TopBar({
  title,
  onToggleRail,
  railOpen,
  status,
  onOpenSettings,
}: TopBarProps) {
  const window = () => getCurrentWindow();
  const brokerLabel = {
    unconfigured: "Broker not configured",
    saved: "Broker saved",
    connected: "Alpaca",
    error: "Broker unreachable",
  }[status.broker];
  const dotColor = {
    unconfigured: "transparent",
    saved: "var(--muted-foreground)",
    connected: "var(--positive)",
    error: "var(--negative)",
  }[status.broker];

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
      <span className="min-w-0 flex-1 truncate text-sm font-medium">{title}</span>
      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          aria-label={brokerLabel}
          onClick={() => onOpenSettings("broker")}
          className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <span
            aria-hidden
            className="size-1.5 rounded-full"
            style={{ background: dotColor }}
          />
          <span className="hidden sm:inline">{brokerLabel}</span>
        </button>
        {status.environment !== null ? (
          <Badge
            variant={status.environment === "live" ? "outline" : "secondary"}
            title={status.environmentVerified ? undefined : "Not verified"}
            className={
              status.environment === "live"
                ? "border-[color:var(--warning)] text-[color:var(--warning)]"
                : undefined
            }
          >
            {status.environment === "live" ? "Live" : "Paper"}
          </Badge>
        ) : null}
      </div>
      {isWindowsDesktop() ? (
        <div className="flex items-center">
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
