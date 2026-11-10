import { useEffect, useReducer, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Button } from "@/components/ui/button";
import { isTauri, setApiBase } from "@/lib/api-base";
import {
  bootReducer,
  initialBootState,
  waitForHealth,
  type BootEvent,
} from "@/lib/desktop";

const EVENT_NAMES = [
  "setup_progress",
  "setup_failed",
  "agent_ready",
  "agent_failed",
] as const;

/**
 * Holds the app behind the first-launch setup and agent startup states.
 *
 * @param props - Children rendered once the agent answers.
 * @returns The boot screen or the app.
 */
export function DesktopBoot({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(bootReducer, initialBootState);

  useEffect(() => {
    if (import.meta.env.DEV || !isTauri()) {
      dispatch({ type: "health_ok", base: "" });
      return;
    }

    let active = true;
    const disposers: Array<() => void> = [];
    const onEvent = (event: BootEvent) => {
      if (active) {
        dispatch(event);
      }
    };

    const start = async () => {
      for (const name of EVENT_NAMES) {
        const unlisten = await listen<Record<string, string>>(name, (event) => {
          const payload = event.payload;
          if (name === "setup_progress") {
            onEvent({ type: name, step: payload.step, line: payload.line });
            return;
          }
          if (name === "agent_ready") {
            onEvent({ type: name, base: payload.base });
            setApiBase(payload.base);
            void waitForHealth(payload.base)
              .then(() => onEvent({ type: "health_ok", base: payload.base }))
              .catch((error: unknown) =>
                onEvent({
                  type: "health_failed",
                  message:
                    error instanceof Error ? error.message : "Health check failed.",
                }),
              );
            return;
          }
          onEvent({
            type: name,
            message: payload.message,
            logPath: payload.log_path,
          });
        });
        disposers.push(unlisten);
      }
      await invoke("bootstrap");
    };

    void start().catch((error: unknown) => {
      dispatch({
        type: "setup_failed",
        message: error instanceof Error ? error.message : "Agent failed to start.",
        logPath: "",
      });
    });

    return () => {
      active = false;
      for (const dispose of disposers) {
        dispose();
      }
    };
  }, []);

  const retry = async () => {
    dispatch({ type: "retry" });
    try {
      await invoke("restart_agent");
    } catch (error) {
      dispatch({
        type: "setup_failed",
        message: error instanceof Error ? error.message : "Restart failed.",
        logPath: "",
      });
    }
  };

  if (state.phase === "ready" || state.phase === "degraded") {
    return (
      <>
        {state.phase === "degraded" ? (
          <div
            role="alert"
            className="flex items-center justify-between gap-3 border-b bg-muted px-4 py-2 text-sm"
          >
            <span className="min-w-0 flex-1">{state.message}</span>
            <Button variant="outline" size="sm" onClick={retry}>
              Retry
            </Button>
          </div>
        ) : null}
        {children}
      </>
    );
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 bg-background p-8 text-sm">
      {state.phase === "failed" ? (
        <>
          <p role="alert">{state.message}</p>
          {state.logPath ? (
            <code className="text-xs text-muted-foreground">{state.logPath}</code>
          ) : null}
          <Button variant="outline" size="sm" onClick={retry}>
            Retry
          </Button>
        </>
      ) : (
        <>
          <p>
            {state.phase === "installing"
              ? "Setting up TradeCopilot"
              : "Starting the agent"}
          </p>
          {state.phase === "installing" ? (
            <p className="max-w-[min(560px,100%)] truncate text-xs text-muted-foreground">
              {state.step}: {state.line}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
