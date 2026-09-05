"use client";

/**
 * Live map. Cameras, activity, and incidents on offline tiles.
 *
 * Tiles come from /tiles/{z}/{x}/{y}.png — plain static files cached by
 * api/scripts/download_tiles.py. Leaflet's default layer fetches from the
 * network on every pan, which on demo day means a blank map.
 *
 * Markers are divIcons (styled HTML) rather than image pins: it avoids the
 * bundler icon-path problem entirely, and the camera state — live, silent,
 * pulsing — is then just CSS.
 */

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, Tooltip } from "react-leaflet";

import { Camera, IncidentListItem, listCameras, listIncidents } from "@/lib/api";
import { subscribeLive } from "@/lib/ws";

/** A camera with no sighting for this long is drawn as silent. */
const SILENT_AFTER_MS = 30_000;

function cameraIcon(active: boolean) {
  return L.divIcon({
    className: "",
    html: `<span style="
      display:block;width:16px;height:16px;border-radius:9999px;
      background:${active ? "#10b981" : "#6b7280"};
      box-shadow:0 0 0 4px ${active ? "rgba(16,185,129,.25)" : "rgba(107,114,128,.2)"};
      ${active ? "animation:tt-pulse 1.2s ease-out infinite;" : ""}
    "></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

const incidentIcon = L.divIcon({
  className: "",
  html: `<span style="
    display:block;width:12px;height:12px;transform:rotate(45deg);
    background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,.3);
  "></span>`,
  iconSize: [12, 12],
  iconAnchor: [6, 6],
});

export default function LiveMap() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [incidents, setIncidents] = useState<IncidentListItem[]>([]);
  const [lastSeen, setLastSeen] = useState<Record<string, number>>({});
  const [, setTick] = useState(0);

  useEffect(() => {
    void listCameras().then(setCameras).catch(() => {});
    void listIncidents().then(setIncidents).catch(() => {});
  }, []);

  useEffect(
    () =>
      subscribeLive((event) => {
        const data = event.data as Record<string, unknown>;
        if (event.type === "sighting") {
          setLastSeen((prev) => ({ ...prev, [String(data.camera_id)]: Date.now() }));
        }
        if (event.type === "incident") {
          void listIncidents().then(setIncidents).catch(() => {});
        }
      }),
    [],
  );

  // Re-render on a timer so a camera fades to silent on its own; nothing
  // arrives to trigger a render when a camera goes quiet.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);

  const centre = useMemo<[number, number]>(() => {
    if (!cameras.length) return [25.011, 67.0403];
    return [
      cameras.reduce((sum, c) => sum + c.lat, 0) / cameras.length,
      cameras.reduce((sum, c) => sum + c.lng, 0) / cameras.length,
    ];
  }, [cameras]);

  const incidentPoints = incidents
    .map((incident) => {
      const camera = cameras.find((c) => c.id === incident.camera.id);
      return camera ? { incident, camera } : null;
    })
    .filter((x): x is { incident: IncidentListItem; camera: Camera } => x !== null);

  return (
    <>
      <style>{`@keyframes tt-pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.5)}70%{box-shadow:0 0 0 14px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}`}</style>
      <MapContainer
        center={centre}
        zoom={14}
        minZoom={13}
        maxZoom={17}
        className="h-[calc(100dvh-6rem)] w-full rounded-lg"
        key={cameras.length} /* recentre once cameras load */
      >
        <TileLayer
          url="/tiles/{z}/{x}/{y}.png"
          minZoom={13}
          maxZoom={17}
          attribution="&copy; OpenStreetMap contributors"
        />

        {cameras.map((camera) => {
          const active = Date.now() - (lastSeen[camera.id] ?? 0) < SILENT_AFTER_MS;
          return (
            <Marker
              key={camera.id}
              position={[camera.lat, camera.lng]}
              icon={cameraIcon(active)}
            >
              <Tooltip>{camera.name}</Tooltip>
              <Popup>
                <div className="text-sm">
                  <div className="font-medium">{camera.name}</div>
                  <div>{active ? "streaming" : "silent"}</div>
                  <div className="text-xs opacity-70">
                    {camera.lat.toFixed(5)}, {camera.lng.toFixed(5)}
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}

        {incidentPoints.map(({ incident, camera }) => (
          <Marker
            key={incident.id}
            position={[camera.lat, camera.lng]}
            icon={incidentIcon}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-medium">{incident.violation.replace(/_/g, " ")}</div>
                <div>{incident.vehicle_type}</div>
                <Link href={`/incidents/${incident.id}`} className="underline">
                  Open incident
                </Link>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </>
  );
}
