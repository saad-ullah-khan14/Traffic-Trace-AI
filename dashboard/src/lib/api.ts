/**
 * The only place the dashboard talks to the backend.
 *
 * Keeping fetch calls here means URLs, headers and error shapes are defined
 * once, and Phase 16's auth hardening touches one file.
 */

import { apiBase } from "./config";

export interface Camera {
  id: string;
  name: string;
  lat: number;
  lng: number;
  heading: number | null;
  created_at?: string;
}

export interface FrameAccepted {
  accepted: boolean;
  queued: number;
  camera: string;
}

export interface WorkerStats {
  queued: number;
  queue_max: number;
  processed: number;
  dropped: number;
  failed: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // Non-JSON error body; the status text will do.
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

/** Identify this phone as a seeded camera, by typing its secret. */
export async function claimCamera(token: string): Promise<Camera> {
  const response = await fetch(`${apiBase()}/api/cameras/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  return unwrap<Camera>(response);
}

/** Report this camera's position, from GPS or a manual correction. */
export async function updateMyLocation(
  token: string,
  lat: number,
  lng: number,
  accuracyM?: number,
): Promise<Camera> {
  const response = await fetch(`${apiBase()}/api/cameras/me/location`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-Camera-Token": token,
    },
    body: JSON.stringify({ lat, lng, accuracy_m: accuracyM ?? null }),
  });
  return unwrap<Camera>(response);
}

/**
 * Upload one captured frame.
 *
 * `capturedAt` is the moment the shutter fired, not the moment this request is
 * sent. After a retry those differ by seconds, and the backend's reachability
 * maths is built on capture time.
 */
export async function postFrame(
  token: string,
  blob: Blob,
  capturedAt: Date,
  signal?: AbortSignal,
): Promise<FrameAccepted> {
  const form = new FormData();
  form.append("frame", blob, "frame.jpg");
  form.append("ts", capturedAt.toISOString());

  const response = await fetch(`${apiBase()}/api/frames`, {
    method: "POST",
    headers: { "X-Camera-Token": token },
    body: form,
    signal,
  });
  return unwrap<FrameAccepted>(response);
}

export async function getWorkerStats(): Promise<WorkerStats> {
  return unwrap<WorkerStats>(await fetch(`${apiBase()}/api/frames/stats`));
}

export async function listCameras(): Promise<Camera[]> {
  return unwrap<Camera[]>(await fetch(`${apiBase()}/api/cameras`));
}

// --- incidents ---------------------------------------------------------

export interface CameraRef {
  id: string;
  name: string;
  lat?: number | null;
  lng?: number | null;
}

export interface Sighting {
  id: string;
  ts: string;
  vehicle_type: string;
  attrs: Record<string, unknown>;
  confidence: number | null;
  crop_url: string | null;
  crop_hash: string | null;
  camera: CameraRef;
}

export interface IncidentListItem {
  id: string;
  violation: string;
  plate_text: string | null;
  status: string;
  created_at: string;
  vehicle_type: string;
  crop_url: string | null;
  camera: CameraRef;
  match_count: number;
}

export interface Match {
  id: string;
  score: number;
  breakdown: Record<string, number>;
  decision: string | null;
  decided_at: string | null;
  sighting: Sighting;
}

export interface IncidentDetail {
  id: string;
  violation: string;
  plate_text: string | null;
  status: string;
  created_at: string;
  sighting: Sighting;
  matches: Match[];
}

export async function listIncidents(status?: string): Promise<IncidentListItem[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return unwrap<IncidentListItem[]>(await fetch(`${apiBase()}/api/incidents${query}`));
}

export async function getIncident(id: string): Promise<IncidentDetail> {
  return unwrap<IncidentDetail>(await fetch(`${apiBase()}/api/incidents/${id}`));
}

export async function decideMatch(matchId: string, decision: "confirm" | "reject") {
  return unwrap(
    await fetch(`${apiBase()}/api/matches/${matchId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...pinHeaders() },
      body: JSON.stringify({ decision }),
    }),
  );
}

/** Crops are served by the API on :8000, not by the dashboard on :3000. */
export function cropSrc(cropUrl: string | null | undefined): string | undefined {
  return cropUrl ? `${apiBase()}${cropUrl}` : undefined;
}

// --- officer PIN -------------------------------------------------------

const PIN_KEY = "traffic_trace.officer_pin";

/** Kept in sessionStorage, not localStorage: closing the browser re-locks it. */
export function getPin(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem(PIN_KEY);
  } catch {
    return null;
  }
}

export function setPin(pin: string): void {
  try {
    sessionStorage.setItem(PIN_KEY, pin);
  } catch {
    /* private mode; the PIN just will not persist */
  }
}

export function clearPin(): void {
  try {
    sessionStorage.removeItem(PIN_KEY);
  } catch {
    /* ignore */
  }
}

function pinHeaders(): Record<string, string> {
  const pin = getPin();
  return pin ? { "X-Officer-Pin": pin } : {};
}

export async function verifyPin(pin: string): Promise<boolean> {
  const response = await fetch(`${apiBase()}/api/admin/verify-pin`, {
    method: "POST",
    headers: { "X-Officer-Pin": pin },
  });
  return response.ok;
}

export async function resetDemo(): Promise<{ sightings_deleted: number; crops_deleted: number }> {
  return unwrap(
    await fetch(`${apiBase()}/api/admin/reset`, {
      method: "POST",
      headers: pinHeaders(),
    }),
  );
}

// --- journeys ----------------------------------------------------------

export interface JourneyStop {
  sighting_id: string;
  camera_id: string;
  camera_name: string | null;
  ts: string;
  lat: number | null;
  lon: number | null;
  hop_confidence: number;
  hop_distance_km: number;
  hop_seconds: number;
  crop_url: string | null;
}

export interface Journey {
  incident_id: string;
  stops: JourneyStop[];
  total_span_seconds: number;
  total_distance_km: number;
}

/** 404 until at least one match is confirmed — one stop is not a journey. */
export async function getJourney(incidentId: string): Promise<Journey | null> {
  const response = await fetch(`${apiBase()}/api/journeys/${incidentId}`);
  if (response.status === 404) return null;
  return unwrap<Journey>(response);
}
// --- Find Me search -----------------------------------------------------

export interface SearchResult {
  sighting_id: string;
  score: number;
  ts: string;
  vehicle_type: string;
  crop_url: string | null;
  frame_url: string | null;
  camera: CameraRef;
}

export interface SearchResponse {
  search_id: string;
  query_detections: number;
  selected_index: number;
  results: SearchResult[];
}

export interface SearchNeedsSelection {
  detail: "multiple_detections";
  detections: { index: number; vehicle_type: string; bbox: number[] }[];
}

/**
 * Upload a photo and search every camera for it.
 * If the photo has more than one vehicle, the API returns
 * `{ detail: "multiple_detections", detections: [...] }` instead of results —
 * call again with `selectIndex` set to the one the officer means.
 */
export async function searchByPhoto(
  file: File,
  mode: "vehicle" | "person",
  options: {
    fromTs?: string;
    toTs?: string;
    cameraIds?: string[];
    vehicleType?: string;
    selectIndex?: number;
  } = {},
): Promise<SearchResponse | SearchNeedsSelection> {
  const form = new FormData();
  form.append("image", file);
  form.append("mode", mode);
  if (options.fromTs) form.append("from_ts", options.fromTs);
  if (options.toTs) form.append("to_ts", options.toTs);
  if (options.vehicleType) form.append("vehicle_type", options.vehicleType);
  if (options.selectIndex !== undefined) form.append("select_index", String(options.selectIndex));
  for (const id of options.cameraIds ?? []) form.append("camera_ids", id);

  const response = await fetch(`${apiBase()}/api/search`, {
    method: "POST",
    headers: pinHeaders(),
    body: form,
  });
  return unwrap(response);
}

/** Persist an officer's confirm/reject on one Find Me result. */
export async function confirmSearchResult(
  searchId: string,
  sightingId: string,
  decision: "confirm" | "reject",
): Promise<void> {
  await unwrap(
    await fetch(`${apiBase()}/api/search/${searchId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...pinHeaders() },
      body: JSON.stringify({ sighting_id: sightingId, decision }),
    }),
  );
}





