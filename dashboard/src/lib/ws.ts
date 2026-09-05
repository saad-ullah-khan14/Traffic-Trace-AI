/**
 * Live event feed client.
 *
 * Reconnects on its own with backoff. On demo day the API may be restarted, the
 * hotspot may drop, and the laptop may sleep — a feed that needs a manual page
 * refresh to come back is a feed that will be dead when it matters.
 */

import { apiBase } from "./config";

export type LiveEventType =
  | "connected"
  | "sighting"
  | "incident"
  | "match_suggestion"
  | "journey_update";

export interface LiveEvent {
  type: LiveEventType;
  data: Record<string, unknown>;
}

const RECONNECT_MIN_MS = 500;
const RECONNECT_MAX_MS = 10_000;

/**
 * Subscribe to the live feed. Returns an unsubscribe function.
 *
 * `onStatus` reports connectedness so the UI can show it — a silent feed and a
 * quiet street look identical otherwise.
 */
export function subscribeLive(
  onEvent: (event: LiveEvent) => void,
  onStatus?: (connected: boolean) => void,
): () => void {
  let socket: WebSocket | null = null;
  let retryMs = RECONNECT_MIN_MS;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let closed = false;

  const connect = () => {
    if (closed) return;

    const url = apiBase().replace(/^http/, "ws") + "/ws/live";
    socket = new WebSocket(url);

    socket.onopen = () => {
      retryMs = RECONNECT_MIN_MS;
      onStatus?.(true);
    };

    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as LiveEvent);
      } catch {
        // A malformed frame must not kill the subscription.
      }
    };

    socket.onclose = () => {
      onStatus?.(false);
      if (closed) return;
      timer = setTimeout(connect, retryMs);
      retryMs = Math.min(retryMs * 2, RECONNECT_MAX_MS);
    };

    // onerror is always followed by onclose, so reconnecting is handled there.
    socket.onerror = () => socket?.close();
  };

  connect();

  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    socket?.close();
  };
}
