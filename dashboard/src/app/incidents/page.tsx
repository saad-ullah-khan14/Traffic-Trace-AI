"use client";

/**
 * Incident feed. New violations appear here within a second of being detected.
 *
 * Live events carry enough to render a card immediately, so a new incident does
 * not wait on a refetch — on a hotspot that round-trip is the difference
 * between "instant" and "laggy" in front of judges.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PlateBadge } from "@/components/PlateBadge";
import { IncidentListItem, cropSrc, listIncidents } from "@/lib/api";
import { subscribeLive } from "@/lib/ws";

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [flash, setFlash] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setIncidents(await listIncidents());
      setError(null);
    } catch {
      setError("Cannot reach the API. Is it running on port 8000?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(
    () =>
      subscribeLive((event) => {
        if (event.type !== "incident") return;
        const d = event.data as Record<string, unknown>;

        // Render straight from the event, then reconcile in the background so
        // match_count and anything else the event omits catch up.
        setIncidents((prev) => {
          const id = String(d.id);
          if (prev.some((i) => i.id === id)) return prev;
          return [
            {
              id,
              violation: String(d.violation),
              plate_text: (d.plate_text as string | null) ?? null,
              status: String(d.status ?? "open"),
              created_at: String(d.created_at ?? new Date().toISOString()),
              vehicle_type: String(d.vehicle_type ?? ""),
              crop_url: (d.crop_url as string | null) ?? null,
              camera: { id: String(d.camera_id ?? ""), name: "" },
              match_count: 0,
            },
            ...prev,
          ];
        });
        setFlash(String(d.id));
        void refresh();
      }),
    [refresh],
  );

  return (
    <main className="p-6">
      <header className="mb-4 flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Incidents</h1>
        <span className="text-sm text-neutral-500">{incidents.length}</span>
      </header>

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}
      {loading && <p className="text-sm text-neutral-500">Loading…</p>}
      {!loading && incidents.length === 0 && !error && (
        <p className="text-sm text-neutral-500">
          No violations yet. Start a camera at{" "}
          <Link href="/camera" className="underline">
            /camera
          </Link>
          .
        </p>
      )}

      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {incidents.map((incident) => (
          <li key={incident.id}>
            <Link
              href={`/incidents/${incident.id}`}
              className={`flex gap-3 rounded-lg border p-3 transition-colors ${
                flash === incident.id
                  ? "border-amber-500 bg-amber-500/5"
                  : "border-neutral-800 bg-neutral-900 hover:border-neutral-600"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={cropSrc(incident.crop_url)}
                alt={incident.vehicle_type}
                className="h-24 w-24 shrink-0 rounded bg-neutral-800 object-cover"
              />
              <div className="min-w-0 space-y-1">
                <div className="font-medium text-amber-400">
                  {incident.violation.replace(/_/g, " ")}
                </div>
                <PlateBadge plate={incident.plate_text} />
                <div className="truncate text-xs text-neutral-400">
                  {incident.vehicle_type}
                  {incident.camera.name ? ` · ${incident.camera.name}` : ""}
                </div>
                <div className="text-xs text-neutral-500">
                  {new Date(incident.created_at).toLocaleTimeString()} ·{" "}
                  {incident.match_count} candidate
                  {incident.match_count === 1 ? "" : "s"}
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
