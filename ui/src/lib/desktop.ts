/** First-launch setup and agent startup state. */
export type BootState =
  | { phase: "boot" }
  | { phase: "installing"; step: string; line: string }
  | { phase: "starting"; base: string }
  | { phase: "ready"; base: string }
  | { phase: "degraded"; base: string; message: string }
  | { phase: "failed"; message: string; logPath: string };

/** Events emitted by the Rust shell or by health polling. */
export type BootEvent =
  | { type: "setup_progress"; step: string; line: string }
  | { type: "setup_failed"; message: string; logPath: string }
  | { type: "agent_ready"; base: string }
  | { type: "agent_failed"; message: string; logPath: string }
  | { type: "health_ok"; base: string }
  | { type: "health_failed"; message: string }
  | { type: "retry" };

/** State before the first shell event. */
export const initialBootState: BootState = { phase: "boot" };

/**
 * Applies one boot event.
 *
 * @param state - Current boot state.
 * @param event - Shell or health event.
 * @returns The next boot state.
 */
export function bootReducer(state: BootState, event: BootEvent): BootState {
  switch (event.type) {
    case "setup_progress":
      return { phase: "installing", step: event.step, line: event.line };
    case "setup_failed":
      return { phase: "failed", message: event.message, logPath: event.logPath };
    case "agent_ready":
      return { phase: "starting", base: event.base };
    case "health_ok":
      return { phase: "ready", base: event.base };
    case "health_failed":
      return state.phase === "starting"
        ? { phase: "failed", message: event.message, logPath: "" }
        : state;
    case "agent_failed": {
      if (state.phase === "ready" || state.phase === "degraded") {
        return { phase: "degraded", base: state.base, message: event.message };
      }
      return { phase: "failed", message: event.message, logPath: event.logPath };
    }
    case "retry":
      return initialBootState;
  }
}

/**
 * Polls the agent health route until it answers or attempts run out.
 *
 * @param base - Agent origin.
 * @param attempts - Number of polls, 300 ms apart.
 * @throws Error When every poll fails.
 */
export async function waitForHealth(base: string, attempts = 10): Promise<void> {
  let lastError = "The agent did not answer.";
  for (let index = 0; index < attempts; index += 1) {
    try {
      const response = await fetch(`${base}/api/health`);
      if (response.ok) {
        return;
      }
      lastError = `Health check failed with ${response.status}.`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : lastError;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(lastError);
}
