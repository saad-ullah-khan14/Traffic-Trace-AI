"use client";

/**
 * Keeps the phone screen awake while capturing.
 *
 * Without this the screen sleeps after ~30 seconds, the browser throttles
 * timers, and the capture loop quietly stops — the single most likely way a
 * live demo dies without anyone noticing until the feed goes silent.
 *
 * The lock is also re-acquired on visibility change: Android drops it whenever
 * the tab is backgrounded, and it is not restored automatically.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export function useWakeLock(enabled: boolean) {
  const sentinel = useRef<WakeLockSentinel | null>(null);
  const [held, setHeld] = useState(false);
  const [supported, setSupported] = useState(true);

  const acquire = useCallback(async () => {
    if (typeof navigator === "undefined" || !("wakeLock" in navigator)) {
      setSupported(false);
      return;
    }
    // Already holding a live lock: do nothing. Re-requesting would leak the
    // old sentinel, and its stale "release" listener would then fire and flip
    // the status tile to "off" while a lock is actually held.
    if (sentinel.current && !sentinel.current.released) {
      setHeld(true);
      return;
    }
    try {
      const next = await navigator.wakeLock.request("screen");
      // Only this sentinel's release may clear the flag.
      next.addEventListener("release", () => {
        if (sentinel.current === next) setHeld(false);
      });
      sentinel.current = next;
      setHeld(true);
    } catch {
      // Denied, or the tab is not visible. Not fatal — capture still runs
      // while the screen is on, so we degrade rather than fail.
      setHeld(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      sentinel.current?.release().catch(() => {});
      sentinel.current = null;
      setHeld(false);
      return;
    }

    void acquire();

    const onVisible = () => {
      if (document.visibilityState === "visible") void acquire();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      sentinel.current?.release().catch(() => {});
      sentinel.current = null;
    };
  }, [enabled, acquire]);

  return { held, supported };
}
