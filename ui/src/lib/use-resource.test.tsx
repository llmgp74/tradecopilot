import { renderHook, waitFor } from "@testing-library/react";
import { expect, it } from "vitest";
import { useResource } from "./use-resource";

it("loads once when enabled and exposes the value", async () => {
  const { result } = renderHook(() => useResource(async () => 42, true));

  await waitFor(() => expect(result.current.data).toBe(42));
  expect(result.current.error).toBeNull();
  expect(result.current.loading).toBe(false);
});
