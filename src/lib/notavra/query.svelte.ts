// A small stand-in for the parts of TanStack Query the Notavra UI relies on:
// fetch on mount, refetch when the key changes, optional polling, a global
// invalidate after a mutation, and structural sharing (an unchanged result keeps
// its previous object, so effects that depend on it do not re-run on every
// poll). Call createQuery during component setup.

import { untrack } from "svelte";

const bus = $state({ version: 0 });

/** Refetch every mounted query, like queryClient.invalidateQueries(). */
export async function invalidateQueries(): Promise<void> {
  bus.version += 1;
}

export interface Query<T> {
  data: T | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => Promise<void>;
}

interface Options<T> {
  key: () => unknown;
  fn: () => Promise<T>;
  interval?: number | false | (() => number | false);
  enabled?: () => boolean;
}

export function createQuery<T>(options: Options<T>): Query<T> {
  let lastKey: string | undefined;
  let run: () => Promise<void> = async () => {};

  const query = $state({
    data: undefined as T | undefined,
    isPending: true,
    isError: false,
    error: null as unknown,
    refetch: () => run(),
  });

  // Derived values only notify when the result changes, so a new interval or
  // enabled flag computed from polled data does not trigger a fetch by itself.
  const key = $derived(JSON.stringify(options.key()));
  const enabled = $derived(options.enabled ? options.enabled() : true);
  const interval = $derived(typeof options.interval === "function" ? options.interval() : options.interval);

  $effect(() => {
    bus.version; // invalidation refetches without clearing data
    const current = key;
    const on = enabled;

    // A new key is a new query: clear the old result, as TanStack Query does.
    if (current !== lastKey) {
      lastKey = current;
      query.data = undefined;
      query.isPending = true;
      query.isError = false;
      query.error = null;
    }
    if (!on) return;

    let alive = true;
    run = async () => {
      try {
        const data = await untrack(() => options.fn());
        if (alive) {
          const same = untrack(() => query.data !== undefined && JSON.stringify(query.data) === JSON.stringify(data));
          if (!same) query.data = data;
          query.isError = false;
          query.error = null;
        }
      } catch (error) {
        if (alive) {
          query.isError = true;
          query.error = error;
        }
      } finally {
        if (alive) query.isPending = false;
      }
    };
    void run();
    return () => {
      alive = false;
    };
  });

  // Polling restarts when the key or the interval changes, like refetchInterval.
  $effect(() => {
    key;
    const every = interval;
    if (!enabled || !every) return;
    const timer = setInterval(() => void run(), every);
    return () => clearInterval(timer);
  });

  return query;
}
