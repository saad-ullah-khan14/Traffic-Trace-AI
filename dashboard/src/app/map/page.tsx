"use client";

/**
 * Live map page.
 *
 * Leaflet is loaded with ssr:false because it touches `window` at import time
 * and would crash the server render.
 */

import dynamic from "next/dynamic";

const LiveMap = dynamic(() => import("@/components/LiveMap"), {
  ssr: false,
  loading: () => <p className="p-6 text-sm text-neutral-500">Loading map…</p>,
});

export default function MapPage() {
  return (
    <main className="p-6">
      <header className="mb-3 flex items-baseline gap-4">
        <h1 className="text-xl font-semibold">Live map</h1>
        <span className="text-xs text-neutral-500">
          <span className="text-emerald-400">●</span> streaming ·{" "}
          <span className="text-neutral-500">●</span> silent ·{" "}
          <span className="text-amber-400">◆</span> incident
        </span>
      </header>
      <LiveMap />
    </main>
  );
}
