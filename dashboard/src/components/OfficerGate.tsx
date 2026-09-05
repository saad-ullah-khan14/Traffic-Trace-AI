"use client";

/**
 * PIN gate and demo reset, shown in the sidebar.
 *
 * Read-only pages stay open on purpose — the feed and map get projected, and
 * typing a PIN to show them would waste demo time. The PIN is required only for
 * the two actions that change or destroy state: confirming a match, and reset.
 * The API enforces it; this is just the keypad.
 */

import { useEffect, useState } from "react";

import { clearPin, getPin, resetDemo, setPin, verifyPin } from "@/lib/api";

export function OfficerGate() {
  const [unlocked, setUnlocked] = useState(false);
  const [pin, setPinInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => setUnlocked(Boolean(getPin())), []);

  async function unlock(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (await verifyPin(pin)) {
        setPin(pin);
        setUnlocked(true);
        setPinInput("");
      } else {
        setError("Wrong PIN");
      }
    } catch {
      setError("API unreachable");
    } finally {
      setBusy(false);
    }
  }

  async function doReset() {
    setBusy(true);
    try {
      const result = await resetDemo();
      setError(null);
      setConfirming(false);
      // A full reload is the honest way to clear every page's cached state.
      window.location.reload();
      console.log("reset:", result);
    } catch {
      setError("Reset failed");
    } finally {
      setBusy(false);
    }
  }

  if (!unlocked) {
    return (
      <form onSubmit={unlock} className="mt-6 border-t border-neutral-800 pt-4">
        <label className="block text-xs text-neutral-500">Officer PIN</label>
        <input
          value={pin}
          onChange={(e) => setPinInput(e.target.value)}
          type="password"
          inputMode="numeric"
          className="mt-1 w-full rounded border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-sm"
        />
        {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={busy || !pin}
          className="mt-2 w-full rounded bg-neutral-800 py-1.5 text-xs disabled:opacity-40"
        >
          Unlock
        </button>
      </form>
    );
  }

  return (
    <div className="mt-6 space-y-2 border-t border-neutral-800 pt-4">
      <div className="text-xs text-emerald-400">● officer unlocked</div>

      {confirming ? (
        <div className="space-y-1">
          <p className="text-xs text-amber-400">
            Delete all sightings, incidents and matches? Cameras are kept.
          </p>
          <div className="flex gap-1">
            <button
              onClick={doReset}
              disabled={busy}
              className="flex-1 rounded bg-red-700 py-1.5 text-xs disabled:opacity-40"
            >
              Yes, reset
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="flex-1 rounded bg-neutral-800 py-1.5 text-xs"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setConfirming(true)}
          className="w-full rounded border border-red-900 py-1.5 text-xs text-red-400 hover:bg-red-950"
        >
          Reset demo
        </button>
      )}

      <button
        onClick={() => {
          clearPin();
          setUnlocked(false);
        }}
        className="w-full rounded py-1 text-xs text-neutral-600 hover:text-neutral-400"
      >
        Lock
      </button>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
