"use client";

/**
 * Find Me — search every camera for a vehicle or a person by photo.
 *
 * Same review pattern as the incident screen: one big comparison at a time,
 * not a grid. The uploaded photo stays fixed on the left; one candidate at a
 * time appears on the right. "Same vehicle" / "Not the same" — nothing is
 * auto-confirmed, the officer decides, same as everywhere else in this
 * product (FIND_ME_PLAN.md rule 4).
 *
 * The score is never shown as a verdict, only as a rank. Measured on this
 * project's own labelled data: confirmed matches scored 0.853-0.951, rejected
 * ones 0.730-0.930 — overlapping, so a threshold on the number would be a lie.
 * The ORDER is trustworthy (rank-1 3/3), so a ranked shortlist is what this
 * screen shows, never a "match found" badge.
 *
 * Decisions are persisted via confirmSearchResult (POST /api/search/{id}/decision)
 * as they're made, not just held in local state — a page refresh should not
 * lose them, and Phase 5's benchmark needs real officer-labelled pairs to
 * measure against (FIND_ME_PLAN.md rule 1: never measure on synthetic input).
 */

import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";

import {
  confirmSearchResult,
  cropSrc,
  Journey,
  searchByPhoto,
  SearchResponse,
  SearchResult,
} from "@/lib/api";

const JourneyMap = dynamic(() => import("@/components/JourneyMap"), {
  ssr: false,
});

const SHORTLIST = 5;

function timeOf(iso: string) {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Great-circle distance in km — same formula pipeline/journey.py uses,
 * so a Find Me route and an incident's journey never disagree. */
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export default function FindMePage() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [mode, setMode] = useState<"vehicle" | "person">("vehicle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [decisions, setDecisions] = useState<Record<string, "confirm" | "reject">>({});
  const [showAll, setShowAll] = useState(false);
  const [currentId, setCurrentId] = useState<string | null>(null);

  const onFile = useCallback((picked: File | null) => {
    setFile(picked);
    setResponse(null);
    setDecisions({});
    setShowAll(false);
    setCurrentId(null);
    setError(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(picked ? URL.createObjectURL(picked) : null);
  }, [previewUrl]);

  const runSearch = useCallback(async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await searchByPhoto(file, mode);
      if ("detail" in result && result.detail === "multiple_detections") {
        setError(
          "More than one vehicle in that photo — crop it to just the one you mean, then upload again.",
        );
        setResponse(null);
      } else {
        setResponse(result as SearchResponse);
        setDecisions({});
        setShowAll(false);
        const first = (result as SearchResponse).results[0];
        setCurrentId(first ? first.sighting_id : null);
      }
    } catch {
      setError("Search failed. Is the officer PIN unlocked?");
    } finally {
      setBusy(false);
    }
  }, [file, mode]);

  const results = useMemo(() => response?.results ?? [], [response]);
  const pool = useMemo(
    () => (showAll ? results : results.slice(0, SHORTLIST)),
    [results, showAll],
  );
  const hidden = results.length - pool.length;

  const undecided = useMemo(
    () => pool.filter((r) => !decisions[r.sighting_id]),
    [pool, decisions],
  );
  const confirmedCount = useMemo(
    () => Object.values(decisions).filter((d) => d === "confirm").length,
    [decisions],
  );

  // Confirmed hits, reshaped into the same Journey shape the incident map
  // consumes — reusing JourneyMap rather than writing a second map component.
  // Distance/time per hop are REAL (haversine + timestamp diff), not
  // placeholders — FIND_ME_PLAN.md Phase 3's "Done when" requires the
  // correct distance and elapsed time, not just a line on the map.
  const journey: Journey | null = useMemo(() => {
    const confirmed = results.filter((r) => decisions[r.sighting_id] === "confirm");
    if (confirmed.length < 2) return null;
    const sorted = [...confirmed].sort(
      (a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime(),
    );

    let totalDistance = 0;
    const stops = sorted.map((r, i) => {
      let hopDistanceKm = 0;
      let hopSeconds = 0;
      if (i > 0) {
        const prev = sorted[i - 1];
        hopSeconds = (new Date(r.ts).getTime() - new Date(prev.ts).getTime()) / 1000;
        if (
          prev.camera.lat != null && prev.camera.lng != null &&
          r.camera.lat != null && r.camera.lng != null
        ) {
          hopDistanceKm = haversineKm(
            prev.camera.lat, prev.camera.lng, r.camera.lat, r.camera.lng,
          );
          totalDistance += hopDistanceKm;
        }
      }
      return {
        sighting_id: r.sighting_id,
        camera_id: r.camera.id,
        camera_name: r.camera.name,
        ts: r.ts,
        lat: r.camera.lat ?? null,
        lon: r.camera.lng ?? null,
        hop_confidence: r.score,
        hop_distance_km: Math.round(hopDistanceKm * 1000) / 1000,
        hop_seconds: hopSeconds,
        crop_url: r.crop_url,
      };
    });

    const totalSpan =
      (new Date(sorted[sorted.length - 1].ts).getTime() - new Date(sorted[0].ts).getTime()) / 1000;

    return {
      incident_id: "find-me-search",
      stops,
      total_span_seconds: totalSpan,
      total_distance_km: Math.round(totalDistance * 1000) / 1000,
    };
  }, [results, decisions]);

  const current = useMemo(
    () => undecided.find((r) => r.sighting_id === currentId) ?? undecided[0] ?? null,
    [undecided, currentId],
  );

  const decide = useCallback(
    (result: SearchResult, decision: "confirm" | "reject") => {
      setDecisions((prev) => ({ ...prev, [result.sighting_id]: decision }));
      const stillOpen = undecided.filter((r) => r.sighting_id !== result.sighting_id);
      setCurrentId(stillOpen[0]?.sighting_id ?? null);

      // Persist to the database — best-effort, does not block the UI.
      // A failed write here means the audit trail misses one row; it should
      // never mean the officer's review flow stalls.
      if (response?.search_id) {
        void confirmSearchResult(response.search_id, result.sighting_id, decision).catch(() => {
          // Silent: this is an audit/benchmark concern, not something the
          // officer needs to act on mid-review.
        });
      }
    },
    [undecided, response],
  );

  return (
    <main className="p-6">
      <header className="mb-4">
        <h1 className="text-lg font-semibold text-blue-400">Find Me</h1>
        <p className="mt-1 max-w-2xl text-sm text-neutral-500">
          Upload a photo of a vehicle or a person. This searches the fingerprints
          already extracted from every camera — it narrows, it does not decide.
          You confirm what is actually the same vehicle or person.
        </p>
      </header>

      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-neutral-700 px-4 py-2 text-sm hover:bg-neutral-800">
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            />
            {file ? "Change photo" : "Upload photo"}
          </label>

          <div className="flex rounded-lg border border-neutral-700 text-sm">
            <button
              onClick={() => setMode("vehicle")}
              className={`px-3 py-2 ${mode === "vehicle" ? "bg-blue-600 text-white" : "text-neutral-400 hover:bg-neutral-800"}`}
            >
              Find this vehicle
            </button>
            
          </div>

          <button
            onClick={runSearch}
            disabled={!file || busy}
            className="ml-auto rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-40"
          >
            {busy ? "Searching…" : "Search"}
          </button>
        </div>

        {previewUrl && (
          <div className="mt-4 flex items-start gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt="Uploaded query"
              className="h-32 w-48 rounded-lg border border-neutral-800 bg-neutral-800 object-contain"
            />
            {response && (
              <p className="text-xs text-neutral-500">
                {response.query_detections} vehicle{response.query_detections === 1 ? "" : "s"}{" "}
                found in the photo · searching by {mode === "vehicle" ? "vehicle shape" : "rider"}
              </p>
            )}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </section>

      {response && results.length === 0 && (
        <div className="mt-6 rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
          <p className="text-lg font-medium text-neutral-200">No candidates found</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-neutral-500">
            No camera has recorded anything close enough to be worth your time.
            If the cameras never saw it, no search will find it.
          </p>
        </div>
      )}

      {results.length > 0 && (
        <>
          {current ? (
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <Panel
                eyebrow="YOU UPLOADED"
                camera="query photo"
                time=""
                cropUrl={previewUrl}
                alt="Query"
              />
              <Panel
                eyebrow="CANDIDATE"
                camera={current.camera.name}
                time={timeOf(current.ts)}
                cropUrl={cropSrc(current.crop_url) ?? null}
                alt={current.vehicle_type}
              >
                <div className="flex items-center justify-between">
                  <p className="text-xs text-neutral-500">
                    rank score {current.score.toFixed(3)} — order is trustworthy, the number is not
                  </p>
                  {current.frame_url && (
                    <a
                      href={current.frame_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-blue-400 hover:underline"
                    >
                      see the frame →
                    </a>
                  )}
                </div>
              </Panel>
            </div>
          ) : (
            <div className="mt-6 flex flex-col items-center justify-center rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
              <p className="text-lg font-medium text-neutral-200">
                {confirmedCount === 0 ? "Nothing to review" : "All candidates reviewed"}
              </p>
              <p className="mt-2 max-w-sm text-sm text-neutral-500">
                {confirmedCount === 0
                  ? "None of them were confirmed as the same vehicle or person."
                  : `${confirmedCount} sighting${confirmedCount === 1 ? "" : "s"} confirmed as the same vehicle.`}
              </p>
            </div>
          )}

          {current && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                onClick={() => decide(current, "reject")}
                className="min-w-40 rounded-lg border border-neutral-700 py-3 font-medium hover:bg-neutral-800"
              >
                Not the same
              </button>
              <button
                onClick={() => decide(current, "confirm")}
                className="min-w-40 rounded-lg bg-emerald-600 py-3 font-medium hover:bg-emerald-500"
              >
                Same {mode === "vehicle" ? "vehicle" : "person"}
              </button>
              <span className="w-full text-center text-xs text-neutral-600">
                {undecided.length} left to review · {confirmedCount} confirmed
                {hidden > 0 && ` · ${hidden} lower-ranked not shown`}
              </span>
            </div>
          )}

          <div className="mt-6">
            <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-neutral-600">
              {hidden > 0
                ? `Closest ${pool.length} of ${results.length} — click any to review it`
                : `All ${pool.length} candidates — click any to review it`}
              {hidden > 0 && (
                <button
                  onClick={() => setShowAll(true)}
                  className="rounded border border-neutral-700 px-2 py-0.5 text-neutral-400 hover:border-neutral-500 hover:text-neutral-200"
                >
                  show the other {hidden}
                </button>
              )}
            </p>
            <ul className="flex flex-wrap gap-2">
              {pool.map((r) => {
                const decision = decisions[r.sighting_id];
                const state =
                  decision === "confirm"
                    ? "border-emerald-500"
                    : decision === "reject"
                      ? "border-neutral-800 opacity-30"
                      : r.sighting_id === current?.sighting_id
                        ? "border-blue-500"
                        : "border-neutral-700";
                return (
                  <li key={r.sighting_id}>
                    <button
                      onClick={() => setCurrentId(r.sighting_id)}
                      title={`${r.camera.name} · ${r.score.toFixed(3)}`}
                      className={`relative block rounded-lg border-2 ${state} p-0.5 hover:border-blue-400`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={cropSrc(r.crop_url)}
                        alt={r.vehicle_type}
                        className="h-16 w-24 rounded bg-neutral-800 object-cover"
                      />
                      <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 font-mono text-[10px] text-neutral-300">
                        {r.score.toFixed(2)}
                      </span>
                      {decision === "confirm" && (
                        <span className="absolute left-1 top-1 rounded bg-emerald-600 px-1 text-[10px] font-semibold">
                          ✓
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

                    {journey && (
            <div className="mt-8">
              <p className="mb-2 text-xs font-semibold tracking-widest text-blue-400">
                CONFIRMED ROUTE
              </p>
              <p className="mb-2 text-xs text-neutral-500">
                {journey.total_distance_km.toFixed(2)} km total ·{" "}
                {Math.round(journey.total_span_seconds / 60)} min elapsed
              </p>
              {journey.stops.some((s, i) => {
                if (i === 0 || s.hop_seconds <= 0) return false;
                const kmh = (s.hop_distance_km / s.hop_seconds) * 3600;
                return kmh > 60;
              }) && (
                <p className="mb-2 rounded border border-amber-700 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">
                  ⚠ One or more hops would need over 60 km/h — physically
                  implausible, but shown anyway. The officer is searching,
                  not prosecuting, and a wrong-looking hop is information.
                </p>
              )}
              <div className="h-96 overflow-hidden rounded-xl border border-neutral-800">
                <JourneyMap journey={journey} />
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
}

function Panel({
  eyebrow,
  camera,
  time,
  cropUrl,
  alt,
  children,
}: {
  eyebrow: string;
  camera: string;
  time: string;
  cropUrl: string | null;
  alt: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-blue-600/40 bg-neutral-900/60 p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-[11px] font-semibold tracking-widest text-blue-400">{eyebrow}</span>
        <span className="text-xs text-neutral-500">
          {camera}
          {time && ` · ${time}`}
        </span>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={cropUrl ?? undefined}
        alt={alt}
        className="mb-3 h-64 w-full rounded-lg bg-neutral-800 object-contain"
      />
      {children}
    </section>
  );
}
