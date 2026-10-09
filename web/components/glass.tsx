import Link from "next/link";
import type { ReactNode } from "react";

/** Card glass (translucent, no backdrop blur). For chrome-like containers and tappable tiles. */
export function GlassCard({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "li";
}) {
  return <Tag className={`surface-glass p-4 ${className}`}>{children}</Tag>;
}

/** Near-opaque surface for numbers, charts and tables. */
export function DataCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`surface-data p-4 ${className}`}>{children}</div>;
}

export function LargeTitle({ title, lead }: { title: string; lead?: string }) {
  return (
    <header className="mb-5">
      <h1 className="text-[28px] leading-tight font-bold tracking-tight md:text-[34px]">{title}</h1>
      {lead && <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-2">{lead}</p>}
    </header>
  );
}

export function SectionTitle({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="mb-3 text-lg leading-snug font-bold">
      {children}
    </h2>
  );
}

export function Chip({
  children,
  href,
  active = false,
  external = false,
  className = "",
}: {
  children: ReactNode;
  href?: string;
  active?: boolean;
  external?: boolean;
  className?: string;
}) {
  const cls = `press inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-[15px] font-semibold ${
    active ? "bg-accent text-accent-ink" : "surface-glass !rounded-full text-ink"
  } ${className}`;
  if (!href) return <span className={cls}>{children}</span>;
  if (external) {
    return (
      <a href={href} className={cls} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls} prefetch={false}>
      {children}
    </Link>
  );
}

/** Big price with unit; tabular figures so columns of prices align. */
export function PriceBadge({ value, unit, size = "lg" }: { value: string; unit: string; size?: "lg" | "md" }) {
  return (
    <p className="tabular leading-none">
      <span className={size === "lg" ? "text-[40px] font-bold tracking-tight" : "text-2xl font-bold"}>{value}</span>
      <span className="ml-1 text-sm font-medium text-ink-2">{unit}</span>
    </p>
  );
}

/** ▲ / ▼ change pill. Colour is never alone: arrow + sign + words carry the meaning. */
export function TrendPill({ pct, label }: { pct: number | null; label: string }) {
  if (pct === null || !Number.isFinite(pct)) return null;
  const flat = Math.abs(pct) < 0.5;
  const up = pct > 0;
  const tone = flat ? "bg-line text-ink-2" : up ? "bg-good-soft text-good" : "bg-bad-soft text-bad";
  const arrow = flat ? "→" : up ? "▲" : "▼";
  const text = `${up && !flat ? "+" : ""}${pct.toFixed(1)}%`;
  return (
    <span className={`tabular inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[13px] font-semibold ${tone}`}>
      <span aria-hidden="true">{arrow}</span>
      {text}
      <span className="font-normal">{label}</span>
    </span>
  );
}
