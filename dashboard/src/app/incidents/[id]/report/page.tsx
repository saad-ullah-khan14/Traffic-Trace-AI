"use client";

/**
 * Court-style case file for one incident. Printed via the browser (Ctrl+P → PDF).
 *
 * No PDF library: the browser already has a good one, it needs no dependency,
 * no font bundling, and no offline concerns. `print:` utilities in Tailwind
 * handle the differences between screen and paper.
 *
 * The SHA-256 of every image is printed next to it. That is what lets someone
 * verify later that the evidence has not been altered — the file's name IS its
 * hash, so anyone can re-hash the file and compare.
 */

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { IncidentDetail, cropSrc, getIncident } from "@/lib/api";

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getIncident(id).then(setIncident).catch(() => setError("Could not load this incident."));
  }, [id]);

  if (error) return <main className="p-8 text-red-400">{error}</main>;
  if (!incident) return <main className="p-8 text-neutral-500">Loading…</main>;

  const confirmed = incident.matches.filter((m) => m.decision === "confirm");
  const rejected = incident.matches.filter((m) => m.decision === "reject");
  const generated = new Date();

  return (
    <main className="mx-auto max-w-3xl bg-white p-8 text-black print:p-0">
      <div className="mb-4 flex justify-end print:hidden">
        <button
          onClick={() => window.print()}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white"
        >
          Print / Save as PDF
        </button>
      </div>

      <header className="border-b-2 border-black pb-3">
        <h1 className="text-2xl font-bold">Traffic Violation Case File</h1>
        <p className="text-sm">
          Case reference <span className="font-mono">{incident.id}</span>
        </p>
        <p className="text-xs text-neutral-600">
          Generated {generated.toLocaleString()}
        </p>
      </header>

      <section className="mt-6">
        <h2 className="mb-2 font-bold uppercase tracking-wide">1 · Violation</h2>
        <table className="w-full text-sm">
          <tbody>
            <Row label="Offence" value={incident.violation.replace(/_/g, " ")} />
            <Row
              label="Registration plate"
              value={
                incident.plate_text ?? "UNREADABLE — identified by visual fingerprint"
              }
            />
            <Row label="Vehicle" value={incident.sighting.vehicle_type} />
            <Row label="Location" value={incident.sighting.camera.name} />
            <Row
              label="Date and time"
              value={new Date(incident.sighting.ts).toLocaleString()}
            />
            <Row label="Case status" value={incident.status} />
          </tbody>
        </table>
      </section>

      <section className="mt-6 break-inside-avoid">
        <h2 className="mb-2 font-bold uppercase tracking-wide">2 · Evidence</h2>
        <figure className="border border-neutral-300 p-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={cropSrc(incident.sighting.crop_url)}
            alt="Violation evidence"
            className="mx-auto max-h-64 object-contain"
          />
          <figcaption className="mt-2 break-all font-mono text-[10px] text-neutral-600">
            SHA-256: {incident.sighting.crop_hash ?? "—"}
          </figcaption>
        </figure>
        <p className="mt-2 text-xs text-neutral-600">
          Each image is stored under a filename equal to the SHA-256 hash of its own
          contents. Re-computing the hash of the stored file and comparing it with the
          value above demonstrates the image has not been altered since capture.
        </p>
      </section>

      <section className="mt-6">
        <h2 className="mb-2 font-bold uppercase tracking-wide">
          3 · Confirmed sightings of the same vehicle
        </h2>
        {confirmed.length === 0 ? (
          <p className="text-sm text-neutral-600">
            No further sightings have been confirmed by an officer.
          </p>
        ) : (
          <ol className="space-y-3">
            {confirmed.map((match, index) => (
              <li key={match.id} className="flex gap-3 break-inside-avoid border-b pb-3">
                <span className="font-bold">{index + 1}.</span>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={cropSrc(match.sighting.crop_url)}
                  alt=""
                  className="h-20 w-20 border border-neutral-300 object-cover"
                />
                <div className="text-sm">
                  <div className="font-medium">{match.sighting.camera.name}</div>
                  <div>{new Date(match.sighting.ts).toLocaleString()}</div>
                  <div className="text-xs">
                    Match score {match.score.toFixed(3)} ·{" "}
                    {Object.entries(match.breakdown)
                      .map(([k, v]) => `${k} ${v.toFixed(2)}`)
                      .join(" · ")}
                  </div>
                  <div className="break-all font-mono text-[10px] text-neutral-600">
                    {match.sighting.crop_hash}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="mt-6 break-inside-avoid">
        <h2 className="mb-2 font-bold uppercase tracking-wide">4 · Officer decisions</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-black text-left">
              <th className="py-1">Candidate</th>
              <th>Camera</th>
              <th>Score</th>
              <th>Decision</th>
              <th>Decided at</th>
            </tr>
          </thead>
          <tbody>
            {[...confirmed, ...rejected].map((match) => (
              <tr key={match.id} className="border-b border-neutral-300">
                <td className="py-1 font-mono text-[10px]">
                  {match.sighting.id.slice(0, 8)}
                </td>
                <td>{match.sighting.camera.name}</td>
                <td>{match.score.toFixed(3)}</td>
                <td className="font-medium">{match.decision}</td>
                <td>
                  {match.decided_at ? new Date(match.decided_at).toLocaleString() : "—"}
                </td>
              </tr>
            ))}
            {confirmed.length + rejected.length === 0 && (
              <tr>
                <td colSpan={5} className="py-2 text-neutral-600">
                  No decisions recorded.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="mt-6 break-inside-avoid text-xs text-neutral-700">
        <h2 className="mb-2 font-bold uppercase tracking-wide text-black">
          5 · Method and limitations
        </h2>
        <p>
          This vehicle was identified without a readable registration plate. Every
          vehicle passing a camera is recorded with a visual fingerprint; when a
          violation is detected, candidate sightings are narrowed by whether the vehicle
          could physically have travelled between the two cameras in the elapsed time,
          then ranked by visual similarity.
        </p>
        <p className="mt-2">
          <strong>Candidates are proposed by software; every match in this file was
          confirmed by a human officer.</strong> No identification is made automatically.
          Facial recognition is not used. Sightings not linked to an incident are
          deleted after 48 hours.
        </p>
      </section>

      <footer className="mt-8 border-t border-neutral-300 pt-3 text-xs text-neutral-600">
        <div className="flex justify-between">
          <span>Traffic_Trace · case {incident.id.slice(0, 8)}</span>
          <span>Officer signature: ______________________</span>
        </div>
      </footer>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <tr className="border-b border-neutral-200">
      <td className="w-48 py-1 font-medium">{label}</td>
      <td className="py-1">{value}</td>
    </tr>
  );
}
