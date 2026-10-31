/**
 * Whether the API is probably waking from a cold start, as a small store the UI can subscribe to.
 *
 * The API scales to zero, and Modal holds the first request after a quiet spell (it doesn't error) until
 * a container is up, which takes up to about a minute. So a request that has waited a few seconds while
 * the service wasn't known to be awake is "waking" (UI-SPEC §10.3 "Cold start"). Any answer from the API
 * turns it off; a timeout or a network error says the service may be asleep again.
 */

/** A request that has waited this long, with the service not known to be awake, is a wake-up. */
export const WAKING_AFTER_MS = 4_000;
/** After an answer the service counts as awake this long. Longer than the API's idle window, so a lapse can only over-wait. */
export const AWAKE_FOR_MS = 120_000;

export class WakeTracker {
  private lastOkAt: number | null = null;
  private readonly pending = new Map<number, number>();
  private nextId = 0;
  private waking = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly listeners = new Set<() => void>();

  /** `now` is injected for tests. */
  constructor(private readonly now: () => number = Date.now) {}

  /** Whether the API has answered recently, so a long wait is slowness and not a cold start. */
  isAwake(): boolean {
    return this.lastOkAt !== null && this.now() - this.lastOkAt < AWAKE_FOR_MS;
  }

  /** Arrow properties, so they can be passed straight to `useSyncExternalStore`. */
  isWaking = (): boolean => this.waking;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /** A request (with all its retries) started; the returned function ends it, whatever the outcome. */
  begin(): () => void {
    const id = this.nextId++;
    this.pending.set(id, this.now());
    this.update();
    return () => {
      this.pending.delete(id);
      this.update();
    };
  }

  /** The API answered: it is awake. */
  answered(): void {
    this.lastOkAt = this.now();
    this.update();
  }

  /** A timeout or a network error: the service may be asleep, so the next wait is a cold one. */
  lost(): void {
    this.lastOkAt = null;
    this.update();
  }

  /** Recomputes `waking`, and arms one timer for the next moment it could change. */
  private update(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const now = this.now();
    const awake = this.isAwake();
    let waking = false;
    let next = Infinity;
    if (awake && this.lastOkAt !== null && this.pending.size > 0) next = this.lastOkAt + AWAKE_FOR_MS;
    if (!awake) {
      for (const startedAt of this.pending.values()) {
        const due = startedAt + WAKING_AFTER_MS;
        if (due <= now) waking = true;
        else next = Math.min(next, due);
      }
    }
    if (!waking && Number.isFinite(next)) this.timer = setTimeout(() => this.update(), Math.max(0, next - now));
    if (waking !== this.waking) {
      this.waking = waking;
      for (const listener of [...this.listeners]) listener();
    }
  }
}
