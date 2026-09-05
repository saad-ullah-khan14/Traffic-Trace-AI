/**
 * The product's headline, so it is deliberately loud.
 *
 * An unreadable plate is the whole reason this system exists — the badge should
 * read as a designed state, not as missing data.
 */
export function PlateBadge({ plate }: { plate: string | null }) {
  if (plate) {
    return (
      <span className="rounded bg-neutral-800 px-2 py-1 font-mono text-xs text-neutral-200">
        {plate}
      </span>
    );
  }
  return (
    <span className="rounded bg-amber-500/15 px-2 py-1 text-xs font-semibold text-amber-400 ring-1 ring-amber-500/40">
      UNREADABLE · fingerprint mode
    </span>
  );
}
