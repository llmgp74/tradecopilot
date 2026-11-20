import { useCallback, useEffect, useReducer, useState } from "react";
import { toast } from "sonner";
import { invoke } from "@tauri-apps/api/core";
import { Chat } from "@/components/chat/chat";
import { PortfolioDialog } from "@/components/dialogs/portfolio";
import { ProfileDialog } from "@/components/dialogs/profile";
import { JournalDialog } from "@/components/dialogs/journal";
import { SettingsDialog } from "@/components/dialogs/settings";
import { Rail, type DialogName } from "@/components/rail";
import { TopBar } from "@/components/top-bar";
import { ApiError, getPortfolio, getSettings, getThread, listThreads } from "@/lib/api";
import type { AppSettings, ThreadSummary } from "@/lib/api";
import { isTauri } from "@/lib/api-base";
import { deriveConnectionStatus, type BrokerProbe } from "@/lib/connection";
import { isMac } from "@/lib/platform";
import type { SettingsSection } from "@/lib/settings";
import {
  conversationReducer,
  initialConversationState,
  readThreadParam,
} from "@/lib/conversation";

const EMPTY_SETTINGS: AppSettings = {
  model_provider: "",
  model_id: "",
  reasoning_effort: "",
  alpaca_api_key: "",
  alpaca_api_secret: "",
  alpaca_base_url: "",
  fmp_api_key: "",
  finnhub_api_key: "",
  fred_api_key: "",
  edgar_user_agent: "",
  exa_api_key: "",
  tool_permissions: {
    execute: "ask",
    write_file: "auto",
    edit_file: "auto",
    delete: "auto",
  },
  providers: [],
  updated_at: "",
};

/**
 * Application shell. Holds the conversation epoch, thread history, settings,
 * the broker probe, and the single open dialog.
 *
 * @returns The shell.
 */
export default function App() {
  const [conversation, dispatch] = useReducer(
    conversationReducer,
    initialConversationState,
  );
  const [dialog, setDialog] = useState<DialogName | null>(null);
  const [railOpen, setRailOpen] = useState(() => window.innerWidth >= 1024);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [probe, setProbe] = useState<BrokerProbe>("pending");
  const [paper, setPaper] = useState<boolean | null>(null);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("general");
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    const [nextSettings, portfolio] = await Promise.all([
      getSettings().catch(() => null),
      getPortfolio("1D")
        .then((value) => ({ ok: true as const, paper: value.paper }))
        .catch((error: unknown) => ({
          ok: false as const,
          status: error instanceof ApiError ? error.status : 0,
        })),
    ]);
    if (nextSettings !== null) {
      setSettings(nextSettings);
    }
    if (portfolio.ok) {
      setProbe("ok");
      setPaper(portfolio.paper);
    } else if (portfolio.status === 503) {
      setProbe("unconfigured");
      setPaper(null);
    } else {
      setProbe("error");
      setPaper(null);
    }
  }, []);

  const refreshThreads = async () => {
    try {
      const page = await listThreads();
      setThreads(page.items);
    } catch {
      // The rail stays on its last known list; the chat shows its own errors.
    }
  };

  useEffect(() => {
    let active = true;
    void refreshThreads();
    void loadStatus();
    if (isTauri()) {
      void invoke("refresh_model_catalog").catch(() => {});
    }

    const requested = readThreadParam(window.location.search);
    if (requested) {
      void getThread(requested)
        .then((detail) => {
          if (active) {
            dispatch({ type: "open", threadId: requested, messages: detail.messages });
          }
        })
        .catch((error: unknown) => {
          if (!active) {
            return;
          }
          if (error instanceof ApiError && error.status === 503) {
            setLoadError(error.message);
          } else {
            toast.error("Thread not found.");
            window.history.replaceState(null, "", "/");
            dispatch({ type: "new" });
          }
        });
    }
    return () => {
      active = false;
    };
  }, [loadStatus]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const shortcut = isMac() ? event.metaKey : event.ctrlKey;
      if (shortcut && event.key.toLowerCase() === "n") {
        event.preventDefault();
        dispatch({ type: "new" });
        window.history.replaceState(null, "", "/");
      }
      if (shortcut && event.key.toLowerCase() === "b") {
        event.preventDefault();
        setRailOpen((value) => !value);
      }
      if (event.key === "Escape" && dialog === null && railOpen) {
        setRailOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dialog, railOpen]);

  const openThread = async (threadId: string) => {
    try {
      const detail = await getThread(threadId);
      setLoadError(null);
      dispatch({ type: "open", threadId, messages: detail.messages });
      window.history.replaceState(null, "", `/?thread=${threadId}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 503) {
        setLoadError(error.message);
        return;
      }
      toast.error("Thread not found.");
      setLoadError(null);
      window.history.replaceState(null, "", "/");
      dispatch({ type: "new" });
    }
  };

  const startNewChat = () => {
    setLoadError(null);
    dispatch({ type: "new" });
    window.history.replaceState(null, "", "/");
  };

  const handleThreadStarted = (threadId: string) => {
    setLoadError(null);
    dispatch({ type: "started", threadId });
    window.history.replaceState(null, "", `/?thread=${threadId}`);
    void refreshThreads();
  };

  const activeThread = threads.find((item) => item.thread_id === conversation.threadId);
  const dialogChange = (name: DialogName) => (open: boolean) => {
    setDialog(open ? name : null);
    if (!open && name === "settings") {
      // The status header reads state fetched at startup, so refresh after a
      // model or provider is saved.
      void loadStatus();
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Rail
        open={railOpen}
        threads={threads}
        activeThreadId={conversation.threadId}
        onToggle={() => setRailOpen((value) => !value)}
        onNewChat={startNewChat}
        onOpenThread={openThread}
        onOpenDialog={setDialog}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={activeThread?.title ?? "New conversation"}
          onToggleRail={() => setRailOpen((value) => !value)}
          railOpen={railOpen}
          status={deriveConnectionStatus(settings ?? EMPTY_SETTINGS, probe, paper)}
          onOpenSettings={(section) => {
            setSettingsSection(section);
            setDialog("settings");
          }}
        />
        <main className="min-h-0 flex-1">
          <Chat
            key={conversation.epoch}
            epoch={conversation.epoch}
            initialThreadId={conversation.threadId}
            initialMessages={conversation.initialMessages}
            onThreadStarted={handleThreadStarted}
            onTurnFinished={() => void refreshThreads()}
            settings={settings ?? EMPTY_SETTINGS}
            onOpenSettings={(section) => {
              setSettingsSection(section);
              setDialog("settings");
            }}
            onModelChanged={() => void loadStatus()}
            loadError={loadError}
          />
        </main>
      </div>

      <PortfolioDialog
        open={dialog === "portfolio"}
        onOpenChange={dialogChange("portfolio")}
        onOpenSettings={() => setDialog("settings")}
      />
      <ProfileDialog open={dialog === "profile"} onOpenChange={dialogChange("profile")} />
      <JournalDialog open={dialog === "journal"} onOpenChange={dialogChange("journal")} />
      <SettingsDialog
        open={dialog === "settings"}
        initialSection={settingsSection}
        onOpenChange={dialogChange("settings")}
      />
    </div>
  );
}
