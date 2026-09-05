/**
 * Runtime configuration.
 *
 * The API base URL is derived from the browser's own hostname rather than being
 * baked in at build time. On demo day the phone reaches the laptop over a
 * hotspot at an address nobody knows in advance — a hardcoded localhost would
 * work on the laptop and fail on every phone.
 */

export const API_PORT = 8000;

export function apiBase(): string {
  if (typeof window === "undefined") {
    // Server-render pass; no request is made from here.
    return `http://localhost:${API_PORT}`;
  }

  const override = process.env.NEXT_PUBLIC_API_URL;
  if (override) return override.replace(/\/$/, "");

  // Same host the dashboard was loaded from, different port.
  return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
}

/** Where the claimed camera token is kept, so a refresh does not re-prompt. */
export const TOKEN_STORAGE_KEY = "traffic_trace.camera_token";
