import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False on the server and during hydration, true afterwards.
 *
 * Several components share cached queries (e.g. the signed-in user, fetched by the app shell).
 * When a section hydrates after that data has arrived, rendering it straight away would not
 * match the server's loading state; gate cached data on this to keep hydration consistent.
 */
export function useHydrated() {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
