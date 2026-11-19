import { afterEach, expect, it, vi } from "vitest";
import { ApiError, getHealth, listJournal, patchSettings, putProvider } from "./api";

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

  await patchSettings({ model_provider: "deepseek", model_id: "deepseek-flash" });

  expect(fetchMock.mock.calls[0][1].body).toBe(
    JSON.stringify({ model_provider: "deepseek", model_id: "deepseek-flash" }),
  );
});

it("throws ApiError with the detail string", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(async () =>
        jsonResponse({ detail: "No model is configured." }, 503),
      ),
  );

  await expect(getHealth()).rejects.toMatchObject({ status: 503 });
  await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
});

it("writes a provider with its models", async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
  vi.stubGlobal("fetch", fetchMock);

  await putProvider("openai", {
    api_key: "sk",
    base_url: "",
    npm: "@ai-sdk/openai",
    models: [{ id: "gpt-5", name: "GPT-5", tool_call: true, reasoning_options: [] }],
  });

  const [url, init] = fetchMock.mock.calls[0];
  expect(new URL(url, "http://x").pathname).toBe("/api/providers/openai");
  expect(init.method).toBe("PUT");
  expect(JSON.parse(init.body).models[0].id).toBe("gpt-5");
});
