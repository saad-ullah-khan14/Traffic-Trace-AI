"use client";

/**
 * Temporary live-feed monitor. Phase 9 replaces this with the real incident
 * feed; for now it proves the WebSocket bus works and doubles as the thing to
 * open when something looks wrong during a demo.
 */

import { useEffect, useRef, useState } from "react";

import { apiBase } from "@/lib/config";
import { LiveEvent, subscribeLive } from "@/lib/ws";

export default function Home() {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<(LiveEvent & { at: string })[]>([]);
  const counts = useRef<Record<string, number>>({});

  useEffect(() => {
    return subscribeLive((event) => {
      console.log("[live]", event.type, event.data);
      counts.current[event.type] = (counts.current[event.type] ?? 0) + 1;
      setEvents((prev) =>
        [{ ...event, at: new Date().toLocaleTimeString() }, ...prev].slice(0, 50),
      );
    }, setConnected);
  }, []);

  return (
    <main className="min-h-dvh bg-neutral-950 p-6 text-neutral-100">
      <header className="mb-4 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Traffic_Trace · Live feed</h1>
        <span className={connected ? "text-emerald-400" : "text-red-400"}>
          ● {connected ? "connected" : "disconnected"}
        </span>
        <span className="text-sm text-neutral-500">{events.length} events</span>
      </header>

      {events.length === 0 && (
        <p className="text-sm text-neutral-500">
          Waiting for events. Start a camera at{" "}
          <a href="/camera" className="underline">
            /camera
          </a>
          .
        </p>
      )}

      <ul className="space-y-2">
        {events.map((event, i) => (
          <li
            key={i}
            className="flex items-center gap-3 rounded border border-neutral-800 bg-neutral-900 p-2 text-sm"
          >
            <span className="w-20 shrink-0 font-mono text-xs text-neutral-500">
              {event.at}
            </span>
            <span
              className={`w-36 shrink-0 font-medium ${
                event.type === "incident" ? "text-amber-400" : "text-neutral-300"
              }`}
            >
              {event.type}
            </span>
            {typeof event.data.crop_url === "string" && (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                /* crops are served by the API on :8000, not by the dashboard */
                src={`${apiBase()}${event.data.crop_url}`}
                alt=""
                className="h-10 w-10 rounded object-cover"
              />
            )}
            <span className="truncate font-mono text-xs text-neutral-400">
              {JSON.stringify(event.data)}
            </span>
          </li>
        ))}
      </ul>
    </main>
  );
}
