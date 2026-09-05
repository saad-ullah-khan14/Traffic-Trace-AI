"use client";

/**
 * Review screen: one question at a time.
 *
 * The violation on the left, ONE candidate on the right, and a single question
 * between them — same vehicle, or not? This is where the human-in-the-loop
 * claim is actually made good: the system proposes, the officer decides,
 * nothing is auto-confirmed.
 *
 * It used to render every candidate as a grid of small cards. That showed the
 * work but not the decision, and a grid of eight bikes is not a question, it is
 * a search result. One big pair is a question.
 *
 * After a confirm the next candidate is chosen from a camera that has not been
 * confirmed yet, so a route builds up camera by camera — A, then B, then C —
 * rather than offering four more frames of the camera just confirmed.
 *
 * Keyboard shortcuts exist because reviewing twenty candidates with a mouse is
 * slow, and slow is what the judges will see.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PlateBadge } from "@/components/PlateBadge";
import { IncidentDetail, Match, cropSrc, decideMatch, getIncident } from "@/lib/api";

/**
 * How many candidates the officer is asked about before the rest are offered.
 *
 * The score cannot be thresholded — measured 1 Sep on the officer's own labels,
 * confirmed matches scored 0.853-0.951 and rejected ones 0.730-0.930, so every
 * candidate cleared any cut worth setting and the screen showed all ten. But the
 * ORDER is trustworthy: the true match ranked first in all three incidents, and
 * the top five held six of the seven confirmed matches.
 *
 * So the shortlist is a rank, not a verdict, and it is soft: nothing is hidden
 * permanently, the rest are one click away. If the ranking is ever wrong the
 * officer can still reach the real vehicle — which a hard cut would have deleted.
 */
const SHORTLIST = 5;

const SIGNAL_LABELS: Record<string, string> = {
  vehicle: "vehicle shape",
  rider: "rider",
  attributes: "colour",
  space_time: "time + distance",
};

function timeOf(iso: string) {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Gap between two sightings, phrased the way an officer would say it. */
function gapBetween(fromIso: string, toIso: string) {
  const seconds = Math.abs(
    (new Date(toIso).getTime() - new Date(fromIso).getTime()) / 1000,
  );
  if (seconds < 90) return `${Math.round(seconds)} seconds later`;
  return `${Math.round(seconds / 60)} minutes later`;
}

export default function IncidentPage() {
  // useParams, not the `params` prop: in this Next version that prop is a
  // Promise, and this screen has to be a client component anyway.
  const { id } = useParams<{ id: string }>();

  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setIncident(await getIncident(id));
      setError(null);
    } catch {
      setError("Could not load this incident.");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const matches = useMemo(() => incident?.matches ?? [], [incident]);

  // Matches arrive best-first from the API. Until the officer asks for the rest,
  // only the top few are in play — for the question, the counter and the strip.
  const [showAll, setShowAll] = useState(false);
  const pool = useMemo(
    () => (showAll ? matches : matches.slice(0, SHORTLIST)),
    [matches, showAll],
  );
  const hidden = matches.length - pool.length;

  const undecided = useMemo(() => pool.filter((m) => !m.decision), [pool]);
  const confirmed = useMemo(
    () => matches.filter((m) => m.decision === "confirm"),
    [matches],
  );

  // Tracking the match id rather than an index: the undecided list shrinks on
  // every decision, and an index into a shrinking list silently skips entries.
  const current = useMemo(
    () => undecided.find((m) => m.id === currentId) ?? undecided[0] ?? null,
    [undecided, currentId],
  );

  useEffect(() => {
    if (!currentId && undecided.length) setCurrentId(undecided[0].id);
  }, [undecided, currentId]);

  /**
   * Prefer a camera nobody has confirmed yet.
   *
   * At 1 fps one pass produces several frames of the same bike at the same
   * camera. Without this, confirming one of them just offers its siblings, and
   * the officer clicks through four near-identical photos before the route
   * grows a single hop.
   */
  const advance = useCallback(
    (afterId: string, fresh: Match[]) => {
      const stillOpen = fresh.filter((m) => !m.decision && m.id !== afterId);
      if (!stillOpen.length) {
        setCurrentId(null);
        return;
      }
      const settled = new Set(
        fresh
          .filter((m) => m.decision === "confirm")
          .map((m) => m.sighting.camera.id),
      );
      const newCamera = stillOpen.find((m) => !settled.has(m.sighting.camera.id));
      setCurrentId((newCamera ?? stillOpen[0]).id);
    },
    [],
  );

  const decide = useCallback(
    async (match: Match, decision: "confirm" | "reject") => {
      if (busy) return;
      setBusy(true);
      try {
        await decideMatch(match.id, decision);
        const updated = await getIncident(id);
        setIncident(updated);
        advance(match.id, updated.matches);
        setError(null);
      } catch {
        setError("Could not save that decision. Is the officer PIN unlocked?");
      } finally {
        setBusy(false);
      }
    },
    [busy, id, advance],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!current) return;
      if (event.key === "c" || event.key === "Enter") void decide(current, "confirm");
      if (event.key === "r" || event.key === "Backspace") void decide(current, "reject");
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        const at = undecided.findIndex((m) => m.id === current.id);
        const step = event.key === "ArrowRight" ? 1 : -1;
        const next = undecided[at + step];
        if (next) setCurrentId(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, decide, undecided]);

  if (error && !incident) return <main className="p-6 text-red-400">{error}</main>;
  if (!incident) return <main className="p-6 text-neutral-500">Loading…</main>;

  const plateWasRead = Boolean(incident.plate_text);

  return (
    <main className="p-6">
      <div className="flex items-center justify-between">
        <Link href="/incidents" className="text-sm text-neutral-500 hover:underline">
          ← Incidents
        </Link>
        <div className="flex items-center gap-2">
          {confirmed.length > 0 && (
            <Link
              href="/journeys"
              className="rounded border border-emerald-700 bg-emerald-500/10 px-3 py-1.5 text-sm text-emerald-300 hover:bg-emerald-500/20"
            >
              View route →
            </Link>
          )}
          <Link
            href={`/incidents/${id}/report`}
            className="rounded border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-800"
          >
            Case file →
          </Link>
        </div>
      </div>

      <header className="mt-3 flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold text-amber-400">
          {incident.violation.replace(/_/g, " ")}
        </h1>
        <PlateBadge plate={incident.plate_text} />
        <span className="text-sm text-neutral-500">
          {incident.sighting.vehicle_type} · {incident.sighting.camera.name} ·{" "}
          {timeOf(incident.sighting.ts)}
        </span>
      </header>

      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      {plateWasRead ? (
        <AnprHandled incident={incident} />
      ) : (
        <>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Panel
              tone="amber"
              eyebrow="THE VIOLATION"
              camera={incident.sighting.camera.name}
              time={timeOf(incident.sighting.ts)}
              cropUrl={incident.sighting.crop_url}
              alt={incident.sighting.vehicle_type}
            >
              <p className="text-sm text-neutral-400">
                Plate unreadable, so this vehicle can only be followed by how it
                looks and where it could have gone.
              </p>
            </Panel>

            {current ? (
              <Panel
                tone="blue"
                eyebrow="SAME VEHICLE?"
                camera={current.sighting.camera.name}
                time={timeOf(current.sighting.ts)}
                cropUrl={current.sighting.crop_url}
                alt={current.sighting.vehicle_type}
              >
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-lg text-blue-300">
                    {current.score.toFixed(3)}
                  </span>
                  <span className="text-xs text-neutral-500">
                    {gapBetween(incident.sighting.ts, current.sighting.ts)}
                  </span>
                </div>
                <div className="mt-2 space-y-1.5">
                  {Object.entries(current.breakdown).map(([label, value]) => (
                    <div key={label} className="flex items-center gap-2">
                      <span className="w-28 shrink-0 text-[11px] text-neutral-500">
                        {SIGNAL_LABELS[label] ?? label}
                      </span>
                      <div className="h-2 flex-1 rounded bg-neutral-800">
                        <div
                          className="h-full rounded bg-blue-500"
                          style={{
                            width: `${Math.max(0, Math.min(1, value)) * 100}%`,
                          }}
                        />
                      </div>
                      <span className="w-10 shrink-0 text-right font-mono text-[11px] text-neutral-500">
                        {value.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              </Panel>
            ) : (
              <AllReviewed confirmedCount={confirmed.length} total={matches.length} />
            )}
          </div>

          {current && (
            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={() => decide(current, "reject")}
                disabled={busy}
                className="min-w-40 rounded-lg bg-neutral-700 py-3 font-medium hover:bg-neutral-600 disabled:opacity-40"
              >
                Not the same
              </button>
              <button
                onClick={() => decide(current, "confirm")}
                disabled={busy}
                className="min-w-40 rounded-lg bg-emerald-600 py-3 font-medium hover:bg-emerald-500 disabled:opacity-40"
              >
                Same vehicle
              </button>
              <span className="w-full text-center text-xs text-neutral-600">
                {undecided.length} left to review · {confirmed.length} confirmed ·
                keys: c = same, r = not, ← → to skip
                {hidden > 0 && ` · ${hidden} lower-ranked not shown`}
              </span>
            </div>
          )}

          {matches.length > 0 && (
            <Filmstrip
              matches={pool}
              total={matches.length}
              hidden={hidden}
              onShowAll={() => setShowAll(true)}
              currentId={current?.id ?? null}
              onPick={setCurrentId}
            />
          )}

          {matches.length === 0 && (
            <div className="mt-8 rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
              <p className="text-lg font-medium text-neutral-200">
                No vehicle close enough to ask about
              </p>
              <p className="mx-auto mt-2 max-w-md text-sm text-neutral-500">
                Other cameras recorded vehicles, but none looked enough like this
                one to be worth your time. Narrowing that down is the job — showing
                you every passing bike would not be.
              </p>
            </div>
          )}
        </>
      )}
    </main>
  );
}

/** One big labelled photo with its own caption block. */
function Panel({
  tone,
  eyebrow,
  camera,
  time,
  cropUrl,
  alt,
  children,
}: {
  tone: "amber" | "blue";
  eyebrow: string;
  camera: string;
  time: string;
  cropUrl: string | null;
  alt: string;
  children: React.ReactNode;
}) {
  const ring = tone === "amber" ? "border-amber-600/40" : "border-blue-600/40";
  const label = tone === "amber" ? "text-amber-400" : "text-blue-400";
  return (
    <section className={`rounded-xl border ${ring} bg-neutral-900/60 p-4`}>
      <div className="mb-2 flex items-baseline justify-between">
        <span className={`text-[11px] font-semibold tracking-widest ${label}`}>
          {eyebrow}
        </span>
        <span className="text-xs text-neutral-500">
          {camera} · {time}
        </span>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={cropSrc(cropUrl)}
        alt={alt}
        className="mb-3 h-64 w-full rounded-lg bg-neutral-800 object-contain"
      />
      {children}
    </section>
  );
}

/** Shown in place of the candidate panel once every candidate is decided. */
function AllReviewed({
  confirmedCount,
  total,
}: {
  confirmedCount: number;
  total: number;
}) {
  return (
    <section className="flex flex-col items-center justify-center rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
      <p className="text-lg font-medium text-neutral-200">
        {total === 0 ? "Nothing to review" : "All candidates reviewed"}
      </p>
      <p className="mt-2 max-w-sm text-sm text-neutral-500">
        {confirmedCount === 0
          ? "None of them were the same vehicle. No route was built."
          : `${confirmedCount} sighting${confirmedCount === 1 ? "" : "s"} confirmed as the same vehicle.`}
      </p>
      {confirmedCount > 0 && (
        <Link
          href="/journeys"
          className="mt-4 rounded-lg bg-emerald-600 px-5 py-2.5 font-medium hover:bg-emerald-500"
        >
          See the route
        </Link>
      )}
    </section>
  );
}

/** The shortlist as thumbnails, so the officer can jump back to any of them. */
function Filmstrip({
  matches,
  total,
  hidden,
  onShowAll,
  currentId,
  onPick,
}: {
  matches: Match[];
  total: number;
  hidden: number;
  onShowAll: () => void;
  currentId: string | null;
  onPick: (id: string) => void;
}) {
  return (
    <div className="mt-6">
      <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-neutral-600">
        {hidden > 0
          ? `Closest ${matches.length} of ${total} — click any to review it`
          : `All ${matches.length} candidates — click any to review it`}
        {hidden > 0 && (
          <button
            onClick={onShowAll}
            className="rounded border border-neutral-700 px-2 py-0.5 text-neutral-400 hover:border-neutral-500 hover:text-neutral-200"
          >
            show the other {hidden}
          </button>
        )}
      </p>
      <ul className="flex flex-wrap gap-2">
        {matches.map((match) => {
          const state =
            match.decision === "confirm"
              ? "border-emerald-500"
              : match.decision === "reject"
                ? "border-neutral-800 opacity-30"
                : match.id === currentId
                  ? "border-blue-500"
                  : "border-neutral-700";
          return (
            <li key={match.id}>
              <button
                onClick={() => onPick(match.id)}
                title={`${match.sighting.camera.name} · ${match.score.toFixed(3)}`}
                className={`relative block rounded-lg border-2 ${state} p-0.5 hover:border-blue-400`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={cropSrc(match.sighting.crop_url)}
                  alt={match.sighting.vehicle_type}
                  className="h-16 w-24 rounded bg-neutral-800 object-cover"
                />
                <span className="absolute bottom-1 right-1 rounded bg-black/70 px-1 font-mono text-[10px] text-neutral-300">
                  {match.score.toFixed(2)}
                </span>
                {match.decision === "confirm" && (
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
  );
}

/**
 * The other half of the product boundary.
 *
 * A readable plate means the existing ANPR system already has what it needs, so
 * there is deliberately nothing to review here. Saying that plainly is better
 * than an empty candidate list, which reads as a failure.
 */
function AnprHandled({ incident }: { incident: IncidentDetail }) {
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <section className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
        <div className="mb-2 text-[11px] font-semibold tracking-widest text-neutral-500">
          THE VIOLATION
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={cropSrc(incident.sighting.crop_url)}
          alt={incident.sighting.vehicle_type}
          className="h-64 w-full rounded-lg bg-neutral-800 object-contain"
        />
      </section>

      <section className="flex flex-col items-center justify-center rounded-xl border border-neutral-800 bg-neutral-900/60 p-8 text-center">
        <div className="font-mono text-3xl tracking-widest text-neutral-100">
          {incident.plate_text}
        </div>
        <p className="mt-4 text-lg font-medium text-neutral-200">
          Plate read — handled by ANPR
        </p>
        <p className="mt-2 max-w-sm text-sm text-neutral-500">
          Fingerprint matching was not run. Where the plate is legible the
          existing system already issues the ticket, so this feature stays out of
          its way. It only takes over when the plate cannot be read.
        </p>
      </section>
    </div>
  );
}
