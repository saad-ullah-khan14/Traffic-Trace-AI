"use client";

/**
 * The route a vehicle took, drawn hop by hop.
 *
 * This is the demo's closing image, so it animates: the line grows from camera
 * to camera rather than appearing all at once. A static polyline shows the same
 * information and lands with none of the force.
 *
 * Straight lines between cameras, not road paths. Honest about what is known —
 * the system knows the vehicle was at A then at B, not which streets it took.
 */

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip } from "react-leaflet";

import { Journey, cropSrc } from "@/lib/api";

const HOP_MS = 1100;

function stopIcon(index: number, isLast: boolean) {
  const colour = index === 0 ? "#f59e0b" : isLast ? "#10b981" : "#3b82f6";
  return L.divIcon({
    className: "",
    html: `<span style="
      display:flex;align-items:center;justify-content:center;
      width:24px;height:24px;border-radius:9999px;
      background:${colour};color:#000;font:600 12px system-ui;
      box-shadow:0 0 0 4px ${colour}33;
    ">${index + 1}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

export default function JourneyMap({ journey }: { journey: Journey }) {
  const stops = useMemo(
    () => journey.stops.filter((s) => s.lat != null && s.lon != null),
    [journey],
  );

  // How many stops are currently revealed. Restarts whenever the journey grows,
  // so confirming another match replays the route including the new hop.
  const [shown, setShown] = useState(1);

  useEffect(() => {
    setShown(1);
    if (stops.length < 2) return;
    const id = setInterval(
      () => setShown((n) => (n >= stops.length ? n : n + 1)),
      HOP_MS,
    );
    return () => clearInterval(id);
  }, [stops.length]);

  const visible = stops.slice(0, shown);
  const line = visible.map((s) => [s.lat as number, s.lon as number] as [number, number]);

  const centre = useMemo<[number, number]>(() => {
    if (!stops.length) return [25.011, 67.0403];
    return [
      stops.reduce((sum, s) => sum + (s.lat as number), 0) / stops.length,
      stops.reduce((sum, s) => sum + (s.lon as number), 0) / stops.length,
    ];
  }, [stops]);

  if (stops.length === 0) {
    return <p className="text-sm text-neutral-500">No positioned stops to draw.</p>;
  }

  return (
    <div className="space-y-3">
      <MapContainer
        center={centre}
        zoom={14}
        minZoom={13}
        maxZoom={17}
        className="h-[60dvh] w-full rounded-lg"
      >
        <TileLayer
          url="/tiles/{z}/{x}/{y}.png"
          minZoom={13}
          maxZoom={17}
          attribution="&copy; OpenStreetMap contributors"
        />

        {line.length > 1 && (
          <Polyline positions={line} pathOptions={{ color: "#3b82f6", weight: 4, opacity: 0.9 }} />
        )}

        {visible.map((stop, index) => (
          <Marker
            key={stop.sighting_id}
            position={[stop.lat as number, stop.lon as number]}
            icon={stopIcon(index, index === stops.length - 1)}
          >
            <Tooltip>{stop.camera_name ?? "camera"}</Tooltip>
            <Popup>
              <div className="space-y-1 text-sm">
                <div className="font-medium">{stop.camera_name}</div>
                <div>{new Date(stop.ts).toLocaleTimeString()}</div>
                {index > 0 && (
                  <div className="text-xs">
                    {stop.hop_distance_km.toFixed(2)} km ·{" "}
                    {Math.round(stop.hop_seconds)} s · confidence{" "}
                    {stop.hop_confidence.toFixed(2)}
                  </div>
                )}
                {stop.crop_url && (
                  /* eslint-disable-next-line @next/next/no-img-element */
                  <img src={cropSrc(stop.crop_url)} alt="" className="h-16 w-16 object-cover" />
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* Thumbnails along the route, in the order they were seen. */}
      <ol className="flex flex-wrap gap-2">
        {stops.map((stop, index) => (
          <li
            key={stop.sighting_id}
            className={`rounded border p-2 transition-opacity ${
              index < shown ? "border-neutral-700 opacity-100" : "border-neutral-900 opacity-25"
            }`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={cropSrc(stop.crop_url)}
              alt=""
              className="h-16 w-16 rounded bg-neutral-800 object-cover"
            />
            <div className="mt-1 text-[10px] text-neutral-400">
              {index + 1}. {stop.camera_name}
            </div>
            <div className="text-[10px] text-neutral-500">
              {new Date(stop.ts).toLocaleTimeString()}
            </div>
            {index > 0 && (
              <div className="text-[10px] text-blue-400">
                {stop.hop_distance_km.toFixed(2)} km · {stop.hop_confidence.toFixed(2)}
              </div>
            )}
          </li>
        ))}
      </ol>

      <button
        onClick={() => setShown(1)}
        className="rounded border border-neutral-700 px-3 py-1.5 text-xs hover:bg-neutral-800"
      >
        Replay route
      </button>
    </div>
  );
}
