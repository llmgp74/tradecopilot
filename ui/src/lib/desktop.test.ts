import { afterEach, expect, it, vi } from "vitest";
import { bootReducer, initialBootState, waitForHealth } from "./desktop";
import type { BootState } from "./desktop";

afterEach(() => vi.unstubAllGlobals());

it("moves from boot to installing on progress", () => {
  const state = bootReducer(initialBootState, {
    type: "setup_progress",
    step: "python",
    line: "Installed CPython 3.13",
  });
  expect(state).toEqual({
    phase: "installing",
    step: "python",
    line: "Installed CPython 3.13",
  });
});

it("moves from installing to starting when the agent reports a base", () => {
  const installing: BootState = {
    phase: "installing",
    step: "deps",
    line: "",
  };
  expect(
    bootReducer(installing, {
      type: "agent_ready",
      base: "http://127.0.0.1:52143",
    }),
  ).toEqual({ phase: "starting", base: "http://127.0.0.1:52143" });
});

it("keeps the app mounted and degrades on a late crash", () => {
  const ready: BootState = { phase: "ready", base: "http://127.0.0.1:1" };
  expect(
    bootReducer(ready, {
      type: "agent_failed",
      message: "agent exited",
      logPath: "/tmp/agent.log",
    }),
  ).toEqual({
    phase: "degraded",
    base: "http://127.0.0.1:1",
    message: "agent exited",
  });
});

it("fails setup to the error screen", () => {
  expect(
    bootReducer(initialBootState, {
      type: "setup_failed",
      message: "Could not download uv.",
      logPath: "/tmp/agent.log",
    }),
  ).toEqual({
    phase: "failed",
    message: "Could not download uv.",
    logPath: "/tmp/agent.log",
  });
});

it("fails hard when the agent dies before ready", () => {
  expect(
    bootReducer(initialBootState, {
      type: "agent_failed",
      message: "no port",
      logPath: "/tmp/agent.log",
    }),
  ).toEqual({ phase: "failed", message: "no port", logPath: "/tmp/agent.log" });
});

it("retries from failed back to boot", () => {
  const failed: BootState = {
    phase: "failed",
    message: "x",
    logPath: "/tmp/agent.log",
  };
  expect(bootReducer(failed, { type: "retry" })).toEqual({ phase: "boot" });
});

it("health polling tolerates one early failure", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(new Response("", { status: 503 }))
    .mockResolvedValueOnce(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  await waitForHealth("http://127.0.0.1:52143");

  expect(fetchMock).toHaveBeenCalledTimes(2);
});
