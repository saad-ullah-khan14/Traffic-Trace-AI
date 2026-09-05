"use client";

/**
 * App shell: sidebar + live-connection indicator.
 *
 * The connection dot is not decoration. A quiet street and a dead WebSocket
 * look identical on a feed, and on demo day the difference matters within
 * seconds.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { AlertToasts } from "@/components/AlertToasts";
import { OfficerGate } from "@/components/OfficerGate";
import { subscribeLive } from "@/lib/ws";

const NAV = [
  { href: "/", label: "Live feed" },
  { href: "/incidents", label: "Incidents" },
  { href: "/map", label: "Live map" },
  { href: "/journeys", label: "Journeys" },
  { href: "/camera", label: "Camera" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [connected, setConnected] = useState(false);

  useEffect(() => subscribeLive(() => {}, setConnected), []);

  return (
    <div className="flex min-h-dvh bg-neutral-950 text-neutral-100">
      <aside className="hidden w-52 shrink-0 border-r border-neutral-800 p-4 sm:block">
        <div className="mb-6">
          <div className="font-semibold">Traffic_Trace</div>
          <div className={`text-xs ${connected ? "text-emerald-400" : "text-red-400"}`}>
            ● {connected ? "live" : "offline"}
          </div>
        </div>
        <nav className="space-y-1">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded px-3 py-2 text-sm ${
                  active
                    ? "bg-neutral-800 text-white"
                    : "text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <OfficerGate />
      </aside>
      <div className="min-w-0 flex-1">{children}</div>
      {/* Shell-level so a reappearance interrupts whatever page is open. */}
      <AlertToasts />
    </div>
  );
}
