import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

/** State returned by {@link useResource}. */
export interface ResourceState<T> {
  /** Loaded value, or null before the first success. */
  data: T | null;
  /** Server or network error text. */
  error: string | null;
  /** HTTP status of the last failure, when the server answered. */
  errorStatus: number | null;
  /** True while a request is in flight. */
  loading: boolean;
  /** Runs the loader again. */
  reload: () => void;
}

/**
 * Loads one resource when enabled and keeps the last result.
 *
 * Results from an unmounted component or a superseded load are discarded.
 *
 * @param load - Loader function. Recreated loaders are fine; the hook only
 *   reruns on `enabled` and `reload`.
 * @param enabled - When false, the loader does not run.
 * @returns The resource state and a reload callback.
 */
export function useResource<T>(load: () => Promise<T>, enabled = true): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    load()
      .then((value) => {
        if (active) {
          setData(value);
        }
      })
      .catch((cause: unknown) => {
        if (!active) {
          return;
        }
        setError(cause instanceof ApiError ? cause.message : "Request failed.");
        setErrorStatus(cause instanceof ApiError ? cause.status : null);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
    // The loader identity is intentionally ignored; callers pass a fresh one
    // every render and drive refetches through `reload` or `enabled`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, tick]);

  return { data, error, errorStatus, loading, reload };
}
