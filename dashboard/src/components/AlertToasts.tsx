"use client";

/**
 * Reappearance alerts, shown on every page.
 *
 * The moment that sells this system: a vehicle that fled a violation at one
 * camera is spotted again at another, and the officer is told while it is still
 * there. So the toast lives in the shell rather than on one page — if it only
 * appeared on the incidents screen, the alert would arrive while someone was
 * looking at the map, which is exactly when it matters.
 *
 * No toast library: a fixed-position list and a timeout is the whole feature.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { cropSrc } from "@/lib/api";
import { subscribeLive } from "@/lib/ws";

const VISIBLE_MS = 12_000;

interface Alert {
  key: number;
  incidentId: string;
  cameraName: string;
  score: number;
  cropUrl: string | null;
}

export function AlertToasts() {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(
    () =>
      subscribeLive((event) => {
        if (event.type !== "match_suggestion") return;
        const data = event.data as Record<string, unknown>;
        // Only reappearances interrupt. Ordinary candidate lists are produced
        // for every incident and would be constant noise.
        if (!data.reappearance) return;

        const alert: Alert = {
          key: Date.now() + Math.random(),
          incidentId: String(data.incident_id),
          cameraName: String(data.camera_name ?? "a camera"),
          score: Number(data.score ?? 0),
          cropUrl: (data.crop_url as string | null) ?? null,
        };
        setAlerts((prev) => [alert, ...prev].slice(0, 4));
        setTimeout(
          () => setAlerts((prev) => prev.filter((a) => a.key !== alert.key)),
          VISIBLE_MS,
        );
      }),
    [],
  );

  if (alerts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[1000] w-80 space-y-2">
      {alerts.map((alert) => (
        <Link
          key={alert.key}
          href={`/incidents/${alert.incidentId}`}
          onClick={() => setAlerts((prev) => prev.filter((a) => a.key !== alert.key))}
          className="flex gap-3 rounded-lg border border-amber-500/60 bg-neutral-900 p-3 shadow-lg ring-1 ring-amber-500/20 hover:border-amber-400"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={cropSrc(alert.cropUrl)}
            alt=""
            className="h-14 w-14 shrink-0 rounded bg-neutral-800 object-cover"
          />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-amber-400">
              Possible reappearance
            </div>
            <div className="truncate text-xs text-neutral-300">{alert.cameraName}</div>
            <div className="text-xs text-neutral-500">
              match {alert.score.toFixed(2)} · tap to review
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
