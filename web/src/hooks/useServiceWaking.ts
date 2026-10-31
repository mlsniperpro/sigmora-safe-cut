"use client";
import { useSyncExternalStore } from "react";
import { getClient } from "@/lib/client";

/** Whether the API is probably waking from a cold start: a request has waited a few seconds and nothing has answered yet. */
export function useServiceWaking(): boolean {
  const { wake } = getClient();
  // The server render and hydration say "not waking": no request has been sent by then.
  return useSyncExternalStore(wake.subscribe, wake.isWaking, () => false);
}
