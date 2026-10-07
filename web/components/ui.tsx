import type { ReactNode } from "react";

export function Page({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return (
    <main id="main" className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="text-2xl leading-snug font-bold">{title}</h1>
      {intro && <p className="mt-2 leading-relaxed text-muted">{intro}</p>}
      <div className="mt-6 space-y-8">{children}</div>
    </main>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-lg font-bold">{title}</h2>
      {children}
    </section>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line p-4 ${className}`}>{children}</div>;
}

export function Empty({ text }: { text: string }) {
  return <p className="rounded-xl border border-dashed border-line p-6 text-center text-muted">{text}</p>;
}

export function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full text-left text-sm">
        <thead className="text-muted">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="border-b border-line px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {r.map((c, j) => (
                <td key={j} className="px-3 py-2 align-top">
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
