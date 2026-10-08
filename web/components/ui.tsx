import type { ReactNode } from "react";
import { LargeTitle, SectionTitle } from "@/components/glass";

// Shared page scaffolding (same API as Phase 4; restyled for the glass design system).

export function Page({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return (
    <main id="main" className="mx-auto max-w-5xl px-4 pt-6">
      <LargeTitle title={title} lead={intro} />
      <div className="space-y-8">{children}</div>
    </main>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      {children}
    </section>
  );
}

/** Data card: near-opaque so numbers keep full contrast. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`surface-data p-4 ${className}`}>{children}</div>;
}

export function Empty({ text }: { text: string }) {
  return <p className="surface-data p-6 text-center text-ink-2">{text}</p>;
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="surface-data overflow-x-auto">
      <table className="tabular w-full text-left text-[15px]">
        <thead className="text-[13px] text-ink-2">
          <tr>
            {head.map((h, i) => (
              <th key={`${h}-${i}`} scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2.5 align-top">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
