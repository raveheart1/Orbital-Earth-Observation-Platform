"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export type FetchState<T> =
  | { status: "idle"; data: null; error: null }
  | { status: "loading"; data: null; error: null }
  | { status: "ok"; data: T; error: null }
  | { status: "error"; data: null; error: string };

export interface UseFetchResult<T> {
  state: FetchState<T>;
  reload: () => void;
}

/**
 * Minimal client-side data hook: runs `fn` when `enabled`, exposes
 * loading/error/data plus a `reload` for retry buttons. `deps` restarts
 * the fetch when inputs change.
 */
export function useFetch<T>(
  fn: () => Promise<T>,
  deps: readonly unknown[],
  enabled = true,
): UseFetchResult<T> {
  const [state, setState] = useState<FetchState<T>>(
    enabled
      ? { status: "loading", data: null, error: null }
      : { status: "idle", data: null, error: null },
  );
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle", data: null, error: null });
      return;
    }
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });
    fnRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ status: "ok", data, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof ApiError || err instanceof Error
            ? err.message
            : "Something went wrong while loading data.";
        setState({ status: "error", data: null, error: message });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- deps is a caller-provided dependency list
  }, [enabled, tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { state, reload };
}
