"use client";

/**
 * The phone page. Opened on each camera phone at /camera.
 *
 * Flow, as agreed 18 Aug 2026:
 *   1. operator types that camera's secret  -> POST /api/cameras/claim
 *   2. phone reports its GPS fix            -> PATCH /api/cameras/me/location
 *   3. capture loop starts                  -> POST /api/frames
 *
 * Everything on this page is built around one assumption: it will be running
 * unattended on a phone on a tripod, on a hotspot, with nobody watching it. So
 * it must recover from dropped frames, dropped network and a locked screen on
 * its own, and show enough status that a glance tells you it is alive.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useWakeLock } from "@/hooks/useWakeLock";
import { ApiError, Camera, claimCamera, postFrame, updateMyLocation } from "@/lib/api";
import { TOKEN_STORAGE_KEY } from "@/lib/config";
import {
  MOTION_THRESHOLD,
  meanAbsoluteDifference,
  toGreyscaleThumbnail,
} from "@/lib/motion";

const IDLE_INTERVAL_MS = 2000; // 1 frame / 2s when nothing is happening
const BURST_INTERVAL_MS = 1000; // 1 fps while movement continues.
// Measured: process_frame costs 0.3-2 s per frame on this CPU, so the single
// worker sustains ~0.6-1 fps in total. At 250 ms three bursting phones asked
// for 12 fps, saturating the 64-deep queue in ~6 s and then evicting
// continuously — which drops exactly the frames a violation is happening in.
// 1 fps still catches a vehicle crossing the frame and cuts demand 4x.
const BURST_HOLD_MS = 3000; // keep bursting this long after the last motion
const JPEG_QUALITY = 0.75;
const CAPTURE_WIDTH = 960; // downscaled before upload; the model does not need 4K
const MAX_RETRIES = 3;
// A stream that has died still reports readyState >= 2 and still draws — it
// draws black. Rotating the phone is enough to cause it. Measured 1 Sep: 147
// frames uploaded, every one a 10,388-byte pure-black JPEG, while the page
// looked perfectly healthy and the server logged "0 detected" 147 times.
// If the brightest pixel in the whole motion thumbnail is under this, there is
// no picture — not a dark one, none.
const BLANK_LUMA = 8;
// Don't thrash the camera if it genuinely will not come back.
const RESTART_COOLDOWN_MS = 4000;

type Phase = "claim" | "locate" | "streaming";

interface UploadState {
  sent: number;
  failed: number;
  dropped: number;
  lastAckAt: Date | null;
  lastError: string | null;
  queuedOnServer: number;
}

export default function CameraPage() {
  const [phase, setPhase] = useState<Phase>("claim");
  const [token, setToken] = useState("");
  const [camera, setCamera] = useState<Camera | null>(null);
  const [claiming, setClaiming] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);

  const [coords, setCoords] = useState<{ lat: number; lng: number; accuracy?: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [manualLat, setManualLat] = useState("");
  const [manualLng, setManualLng] = useState("");

  const [streaming, setStreaming] = useState(false);
  const [bursting, setBursting] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadState>({
    sent: 0,
    failed: 0,
    dropped: 0,
    lastAckAt: null,
    lastError: null,
    queuedOnServer: 0,
  });

  const tokenInput = useRef<HTMLInputElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const captureCanvas = useRef<HTMLCanvasElement | null>(null);
  const motionCanvas = useRef<HTMLCanvasElement | null>(null);
  const previousThumb = useRef<Uint8ClampedArray | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inFlight = useRef(false);
  const burstUntil = useRef(0);
  const loopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const wakeLock = useWakeLock(streaming);

  // Proves JavaScript actually ran. Without it a page that renders perfectly but
  // never hydrates looks identical to a working one — the form just does a plain
  // browser submit, reloads, and clears itself, which reads as "the button does
  // nothing". Cheap to keep: on demo day it answers the same question instantly.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => setHydrated(true), []);

  // Restore a previous claim so a refresh or an accidental back-swipe does not
  // mean re-typing the secret at the roadside.
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (!saved) return;
    setToken(saved);
    claimCamera(saved)
      .then((c) => {
        setCamera(c);
        // Seed the manual fields from the camera's stored position. Without
        // this they stay empty, and Number("") is 0 — which is a *valid*
        // latitude, so "Save position" would silently move the camera to the
        // Atlantic and the reachability gate would return nothing, forever.
        setManualLat(String(c.lat));
        setManualLng(String(c.lng));
        setPhase("locate");
      })
      .catch(() => localStorage.removeItem(TOKEN_STORAGE_KEY));
  }, []);

  // --- step 1: claim ---------------------------------------------------

  async function handleClaim(event: React.FormEvent) {
    event.preventDefault();

    // Read from the DOM as well as from state. Chrome's paste and autofill on
    // Android do not always fire React's onChange, which left the button dead
    // with a visibly filled field — confusing, and it looks like the page is
    // broken. The input is the source of truth here.
    const typed = (tokenInput.current?.value ?? token).trim();
    if (typed.length < 8) {
      setClaimError("Paste the camera secret first.");
      return;
    }
    setToken(typed);

    setClaiming(true);
    setClaimError(null);
    try {
      const claimed = await claimCamera(typed);
      localStorage.setItem(TOKEN_STORAGE_KEY, typed);
      setCamera(claimed);
      setManualLat(String(claimed.lat));
      setManualLng(String(claimed.lng));
      setPhase("locate");
    } catch (error) {
      setClaimError(
        error instanceof ApiError && error.status === 401
          ? "That secret was not recognised."
          : "Could not reach the server. Check you are on the hotspot.",
      );
    } finally {
      setClaiming(false);
    }
  }

  // --- step 2: locate --------------------------------------------------

  const readGps = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setLocationError("This browser exposes no GPS. Enter the position manually.");
      return;
    }
    setLocating(true);
    setLocationError(null);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const next = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracy: position.coords.accuracy,
        };
        setCoords(next);
        setManualLat(next.lat.toFixed(6));
        setManualLng(next.lng.toFixed(6));
        setLocating(false);
      },
      (error) => {
        setLocating(false);
        setLocationError(
          `GPS failed (${error.message}). Enter the position manually — the seeded value is already filled in.`,
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }, []);

  async function saveLocation() {
    const lat = Number(manualLat);
    const lng = Number(manualLng);

    // Blank fields must be rejected explicitly: Number("") is 0, which is a
    // perfectly valid coordinate and would pass every numeric check.
    if (manualLat.trim() === "" || manualLng.trim() === "") {
      setLocationError("Enter a latitude and longitude, or read the GPS.");
      return;
    }
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      setLocationError("Latitude and longitude must be numbers.");
      return;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      setLocationError("Those coordinates are out of range.");
      return;
    }
    if (lat === 0 && lng === 0) {
      setLocationError("(0, 0) is in the Atlantic — read the GPS or type the real position.");
      return;
    }
    try {
      const updated = await updateMyLocation(token, lat, lng, coords?.accuracy);
      setCamera(updated);
      setPhase("streaming");
    } catch {
      setLocationError("Could not save the position. Is the API reachable?");
    }
  }

  // --- step 3: capture -------------------------------------------------

  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" }, // rear camera
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setStreaming(true);
    } catch (error) {
      setCameraError(
        `Camera unavailable: ${(error as Error).message}. ` +
          "On http the Chrome insecure-origin flag must include this exact address.",
      );
    }
  }, []);

  const stopCamera = useCallback(() => {
    setStreaming(false);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (loopTimer.current) clearTimeout(loopTimer.current);
  }, []);

  // Re-acquire the stream. Rotating the phone, or the browser backgrounding the
  // tab, leaves the old track alive but blind; only a fresh getUserMedia fixes
  // it. Cooled down so a camera that is really gone does not spin.
  const lastRestart = useRef(0);
  const restartCamera = useCallback(async () => {
    if (Date.now() - lastRestart.current < RESTART_COOLDOWN_MS) return;
    lastRestart.current = Date.now();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    await startCamera();
  }, [startCamera]);

  const sendFrame = useCallback(
    async (blob: Blob, capturedAt: Date) => {
      // Retry with backoff. A hotspot drops packets constantly; giving up on
      // the first failure would lose most of a demo's frames.
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          const ack = await postFrame(token, blob, capturedAt);
          setUpload((prev) => ({
            ...prev,
            sent: prev.sent + 1,
            dropped: prev.dropped + (ack.accepted ? 0 : 1),
            lastAckAt: new Date(),
            lastError: null,
            queuedOnServer: ack.queued,
          }));
          return;
        } catch (error) {
          // Only transient failures are worth retrying. A 4xx is the server
          // saying this exact request is wrong — a bad token, an empty body, an
          // oversized frame — and it will be just as wrong three attempts
          // later, while the backoff stalls the capture loop for seconds.
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
            setUpload((prev) => ({
              ...prev,
              failed: prev.failed + 1,
              lastError:
                error.status === 401
                  ? "Camera token rejected — re-claim this camera"
                  : `Rejected (${error.status}): ${error.message}`,
            }));
            return;
          }
          if (attempt === MAX_RETRIES) {
            setUpload((prev) => ({
              ...prev,
              failed: prev.failed + 1,
              lastError: (error as Error).message,
            }));
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 300 * 2 ** attempt));
        }
      }
    },
    [token],
  );

  const captureOnce = useCallback(async () => {
    const video = videoRef.current;
    const canvas = captureCanvas.current;
    if (!video || !canvas || video.readyState < 2) return;

    // Motion check first: it decides how soon the next capture happens.
    const thumb = toGreyscaleThumbnail(video, motionCanvas.current!);
    const difference = meanAbsoluteDifference(previousThumb.current, thumb);
    previousThumb.current = thumb;

    // Before anything else: is there a picture at all? A blind stream uploads
    // black frames forever and every one of them is a wasted second of the
    // demo, with nothing on screen to say so.
    if (thumb) {
      let brightest = 0;
      for (let i = 0; i < thumb.length; i++) {
        if (thumb[i] > brightest) brightest = thumb[i];
      }
      if (brightest < BLANK_LUMA) {
        setCameraError(
          "The camera stopped sending a picture — every frame is black. " +
            "Restarting it. This usually happens after rotating the phone; " +
            "if it keeps happening, reload the page.",
        );
        void restartCamera();
        return;
      }
      if (cameraError) setCameraError(null);
    }

    if (difference > MOTION_THRESHOLD) {
      burstUntil.current = Date.now() + BURST_HOLD_MS;
    }
    setBursting(Date.now() < burstUntil.current);

    // Skip if the previous upload is still going, rather than piling requests
    // onto a link that is already struggling.
    if (inFlight.current) return;

    // Undo the device rotation before uploading.
    //
    // getUserMedia hands back frames in the SENSOR's orientation. The <video>
    // element is rotated by the browser for display, so the phone looks correct
    // while the canvas gets the raw, sideways frame — and a motorcycle lying on
    // its side is not a motorcycle to a detector trained on upright images.
    //
    // Measured 1 Sep on a real landscape capture: as uploaded, 0 detections; the
    // same frame rotated 90° counter-clockwise, 2 motorcycles at 122 px and
    // 169 px, both comfortably over MIN_VEHICLE_HEIGHT_PX. Landscape was the
    // right way to hold the phone all along; the picture was arriving sideways.
    //
    // Rotating by -angle covers both landscape directions, so it does not matter
    // which way the phone is turned.
    const angle =
      (typeof screen !== "undefined" && screen.orientation?.angle) ||
      ((window as unknown as { orientation?: number }).orientation ?? 0);
    const turned = ((angle % 360) + 360) % 360;
    const swap = turned === 90 || turned === 270;

    const srcW = video.videoWidth;
    const srcH = video.videoHeight;
    const scale = CAPTURE_WIDTH / (swap ? srcH : srcW);
    canvas.width = Math.round((swap ? srcH : srcW) * scale);
    canvas.height = Math.round((swap ? srcW : srcH) * scale);

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.save();
    if (turned === 90) {
      ctx.translate(0, canvas.height);
      ctx.rotate(-Math.PI / 2);
    } else if (turned === 270) {
      ctx.translate(canvas.width, 0);
      ctx.rotate(Math.PI / 2);
    } else if (turned === 180) {
      ctx.translate(canvas.width, canvas.height);
      ctx.rotate(Math.PI);
    }
    ctx.drawImage(video, 0, 0, srcW * scale, srcH * scale);
    ctx.restore();

    const capturedAt = new Date();
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
    );
    if (!blob) return;

    inFlight.current = true;
    try {
      await sendFrame(blob, capturedAt);
    } finally {
      inFlight.current = false;
    }
  }, [sendFrame, restartCamera, cameraError]);

  // Self-rescheduling loop rather than setInterval: the interval changes with
  // motion, and setInterval would stack callbacks whenever an upload runs long.
  useEffect(() => {
    if (!streaming) return;

    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      await captureOnce();
      if (cancelled) return;
      const interval = Date.now() < burstUntil.current ? BURST_INTERVAL_MS : IDLE_INTERVAL_MS;
      loopTimer.current = setTimeout(tick, interval);
    };
    void tick();

    return () => {
      cancelled = true;
      if (loopTimer.current) clearTimeout(loopTimer.current);
    };
  }, [streaming, captureOnce]);

  // Rotating the phone, or the browser backgrounding the tab, can leave the
  // track alive but blind. Re-acquire on the way back rather than waiting for
  // the blank-frame guard to notice a few seconds of black.
  useEffect(() => {
    if (!streaming) return;
    const wake = () => {
      if (document.visibilityState === "visible") void restartCamera();
    };
    window.addEventListener("orientationchange", wake);
    document.addEventListener("visibilitychange", wake);
    return () => {
      window.removeEventListener("orientationchange", wake);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [streaming, restartCamera]);

  useEffect(() => () => stopCamera(), [stopCamera]);

  // --- render ----------------------------------------------------------

  return (
    <main className="mx-auto min-h-dvh max-w-md bg-neutral-950 p-4 text-neutral-100">
      <header className="mb-4">
        <h1 className="text-lg font-semibold">Traffic_Trace · Camera</h1>
        {camera && <p className="text-sm text-neutral-400">{camera.name}</p>}
        {hydrated ? (
          <p className="text-xs text-emerald-500">● JS ready</p>
        ) : (
          <p className="text-xs text-red-400">
            ● JS NOT running — enable JavaScript in Chrome settings, or the
            buttons on this page will do nothing.
          </p>
        )}
      </header>

      {phase === "claim" && (
        <form onSubmit={handleClaim} className="space-y-3">
          <label className="block text-sm text-neutral-300">
            Camera secret
            <input
              ref={tokenInput}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              onInput={(event) => setToken((event.target as HTMLInputElement).value)}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="paste the token for this camera"
              className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 p-3 font-mono text-sm"
            />
          </label>
          {claimError && <p className="text-sm text-red-400">{claimError}</p>}
          <button
            type="submit"
            disabled={claiming}
            className="w-full rounded bg-blue-600 p-3 font-medium disabled:opacity-40"
          >
            {claiming ? "Checking…" : "Claim this camera"}
          </button>
        </form>
      )}

      {phase === "locate" && (
        <section className="space-y-3">
          <button onClick={readGps} disabled={locating} className="w-full rounded bg-blue-600 p-3 font-medium disabled:opacity-40">
            {locating ? "Reading GPS…" : "Use my GPS location"}
          </button>

          {coords && (
            <p className="text-sm text-neutral-400">
              GPS fix accurate to ±{Math.round(coords.accuracy ?? 0)} m
            </p>
          )}
          {locationError && <p className="text-sm text-amber-400">{locationError}</p>}

          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-neutral-400">
              Latitude
              <input
                value={manualLat}
                onChange={(event) => setManualLat(event.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 p-2 font-mono text-sm"
              />
            </label>
            <label className="text-xs text-neutral-400">
              Longitude
              <input
                value={manualLng}
                onChange={(event) => setManualLng(event.target.value)}
                inputMode="decimal"
                className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 p-2 font-mono text-sm"
              />
            </label>
          </div>

          <button onClick={saveLocation} className="w-full rounded bg-emerald-600 p-3 font-medium">
            Save position and continue
          </button>
        </section>
      )}

      {phase === "streaming" && (
        <section className="space-y-3">
          <div className="relative overflow-hidden rounded bg-black">
            <video ref={videoRef} playsInline muted className="w-full" />
            {bursting && (
              <span className="absolute right-2 top-2 rounded bg-red-600 px-2 py-1 text-xs font-semibold">
                ● BURST
              </span>
            )}
          </div>

          {cameraError && <p className="text-sm text-red-400">{cameraError}</p>}

          {!streaming ? (
            <button onClick={startCamera} className="w-full rounded bg-emerald-600 p-3 font-medium">
              Start streaming
            </button>
          ) : (
            <button onClick={stopCamera} className="w-full rounded bg-neutral-700 p-3 font-medium">
              Stop
            </button>
          )}

          <dl className="grid grid-cols-2 gap-2 text-sm">
            <Stat label="Frames sent" value={upload.sent} />
            <Stat label="Failed" value={upload.failed} tone={upload.failed ? "bad" : "ok"} />
            <Stat label="Server queue" value={upload.queuedOnServer} />
            <Stat label="Dropped by server" value={upload.dropped} tone={upload.dropped ? "warn" : "ok"} />
            <Stat
              label="Last ack"
              value={upload.lastAckAt ? `${Math.round((Date.now() - upload.lastAckAt.getTime()) / 1000)}s ago` : "—"}
            />
            <Stat
              label="Screen lock"
              value={wakeLock.held ? "held" : wakeLock.supported ? "off" : "n/a"}
              tone={wakeLock.held ? "ok" : "warn"}
            />
          </dl>

          {upload.lastError && (
            <p className="text-sm text-amber-400">Last error: {upload.lastError}</p>
          )}
        </section>
      )}

      <canvas ref={captureCanvas} className="hidden" />
      <canvas ref={motionCanvas} className="hidden" />
    </main>
  );
}

function Stat({
  label,
  value,
  tone = "ok",
}: {
  label: string;
  value: string | number;
  tone?: "ok" | "warn" | "bad";
}) {
  const colour =
    tone === "bad" ? "text-red-400" : tone === "warn" ? "text-amber-400" : "text-neutral-100";
  return (
    <div className="rounded border border-neutral-800 bg-neutral-900 p-2">
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className={`font-mono ${colour}`}>{value}</dd>
    </div>
  );
}
