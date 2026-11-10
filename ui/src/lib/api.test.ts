import { afterEach, expect, it, vi } from "vitest";
import { ApiError, getHealth, listJournal, patchSettings } from "./api";

afterEach(() => vi.unstubAllGlobals());

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status });
}

it("builds journal query parameters", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(jsonResponse({ items: [], page_no: 2, page_size: 25, total: 0 }));
  vi.stubGlobal("fetch", fetchMock);

  await listJournal({ status: "filled", ticker: "nvda", pageNo: 2, pageSize: 25 });

  const url = new URL(fetchMock.mock.calls[0][0], "http://x");
  expect(url.pathname).toBe("/api/journal");
  expect(url.searchParams.get("page_no")).toBe("2");
  expect(url.searchParams.get("page_size")).toBe("25");
  expect(url.searchParams.get("status")).toBe("filled");
  expect(url.searchParams.get("ticker")).toBe("nvda");
});

it("sends only the patch fields", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
  vi.stubGlobal("fetch", fetchMock);

  await patchSettings({ agent_model: "deepseek:deepseek-flash" });

  expect(fetchMock.mock.calls[0][1].body).toBe(
    JSON.stringify({ agent_model: "deepseek:deepseek-flash" }),
  );
});

it("throws ApiError with the detail string", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(async () =>
        jsonResponse({ detail: "AGENT_MODEL is not set." }, 503),
      ),
  );

  await expect(getHealth()).rejects.toMatchObject({ status: 503 });
  await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
});
