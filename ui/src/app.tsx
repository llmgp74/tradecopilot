import { useEffect, useReducer, useState } from "react";
import { toast } from "sonner";
import { Chat } from "@/components/chat/chat";
import { PortfolioDialog } from "@/components/dialogs/portfolio";
import { ProfileDialog } from "@/components/dialogs/profile";
import { JournalDialog } from "@/components/dialogs/journal";
import { SettingsDialog } from "@/components/dialogs/settings";
import { Rail, type DialogName } from "@/components/rail";
import { TopBar } from "@/components/top-bar";
import { ApiError, getHealth, getThread, listThreads } from "@/lib/api";
import type { Health, ThreadSummary } from "@/lib/api";
import {
  conversationReducer,
  initialConversationState,
  readThreadParam,
} from "@/lib/conversation";

/**
 * Application shell. Holds the conversation epoch, thread history, and the
 * single open dialog.
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
  const [health, setHealth] = useState<Health | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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
    void getHealth()
      .then((value) => {
        if (active) {
          setHealth(value);
        }
      })
      .catch(() => {});
    void refreshThreads();

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
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        dispatch({ type: "new" });
        window.history.replaceState(null, "", "/");
      }
      if (event.metaKey && event.key.toLowerCase() === "b") {
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
  const dialogChange = (name: DialogName) => (open: boolean) =>
    setDialog(open ? name : null);

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
        />
        <main className="min-h-0 flex-1">
          <Chat
            key={conversation.epoch}
            epoch={conversation.epoch}
            initialThreadId={conversation.threadId}
            initialMessages={conversation.initialMessages}
            onThreadStarted={handleThreadStarted}
            onTurnFinished={() => void refreshThreads()}
            setupRequired={health !== null && health.agent_model === ""}
            onOpenSettings={() => setDialog("settings")}
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
        onOpenChange={dialogChange("settings")}
      />
    </div>
  );
}
