"use client";

/**
 * Journeys: pick a confirmed incident, watch its route draw itself.
 *
 * Only confirmed incidents appear — a journey exists solely because an officer
 * said these sightings are the same vehicle.
 */

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { IncidentListItem, Journey, cropSrc, getJourney, listIncidents } from "@/lib/api";
import { subscribeLive } from "@/lib/ws";

const JourneyMap = dynamic(() => import("@/components/JourneyMap"), {
  ssr: false,
  loading: () => <p className="text-sm text-neutral-500">Loading map…</p>,
});

export default function JourneysPage() {
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [journey, setJourney] = useState<Journey | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    try {
      const confirmed = await listIncidents("confirmed");
      setIncidents(confirmed);
      setSelected((current) => current ?? confirmed[0]?.id ?? null);
    } catch {
      setMessage("Cannot reach the API.");
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const loadJourney = useCallback(async (incidentId: string) => {
    try {
      const result = await getJourney(incidentId);
      setJourney(result);
      setMessage(result ? null : "No confirmed hops yet — confirm a match first.");
    } catch {
      setMessage("Could not load the journey.");
    }
  }, []);

  useEffect(() => {
    if (selected) void loadJourney(selected);
  }, [selected, loadJourney]);

  // A confirm elsewhere grows the route; redraw without a refresh.
  useEffect(
    () =>
      subscribeLive((event) => {
        if (event.type !== "journey_update") return;
        const incidentId = String((event.data as Record<string, unknown>).incident_id);
        void loadList();
        if (incidentId === selected) setJourney(event.data as unknown as Journey);
      }),
    [selected, loadList],
  );

  return (
    <main className="p-6">
      <header className="mb-4 flex flex-wrap items-baseline gap-3">
        <h1 className="text-xl font-semibold">Journeys</h1>
        {journey && (
          <span className="text-sm text-neutral-400">
            {journey.stops.length} stops · {journey.total_distance_km.toFixed(2)} km ·{" "}
            {Math.round(journey.total_span_seconds / 60)} min
          </span>
        )}
      </header>

      {incidents.length === 0 && (
        <p className="text-sm text-neutral-500">
          No confirmed incidents yet. Confirm a candidate on an incident first.
        </p>
      )}

      {incidents.length > 0 && (
        <ul className="mb-4 flex flex-wrap gap-2">
          {incidents.map((incident) => (
            <li key={incident.id}>
              <button
                onClick={() => setSelected(incident.id)}
                className={`flex items-center gap-2 rounded border px-2 py-1.5 text-sm ${
                  selected === incident.id
                    ? "border-blue-500 bg-neutral-900"
                    : "border-neutral-800 bg-neutral-900 hover:border-neutral-600"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={cropSrc(incident.crop_url)}
                  alt=""
                  className="h-8 w-8 rounded bg-neutral-800 object-cover"
                />
                <span>{incident.violation.replace(/_/g, " ")}</span>
                <span className="text-xs text-neutral-500">{incident.camera.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {message && <p className="mb-3 text-sm text-amber-400">{message}</p>}
      {journey && <JourneyMap journey={journey} />}
    </main>
  );
}
