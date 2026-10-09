import { districtName } from "@/lib/crops";
import type { Lang } from "@/lib/i18n";
import { DISTRICTS, MAP_ATTRIBUTION, MAP_VIEWBOX } from "@/lib/kerala-map";

const STEPS = ["var(--color-seq-1)", "var(--color-seq-2)", "var(--color-seq-3)", "var(--color-seq-4)", "var(--color-seq-5)"];

/**
 * Choropleth of the latest price per district (sequential, one hue, 5 classes). Values are also
 * printed on the map and listed below it, so colour is never the only channel.
 */
export function KeralaMap({
  values,
  lang,
  title,
  none,
}: {
  values: Record<string, number>; // district -> Rs./kg
  lang: Lang;
  title: string;
  none: string;
}) {
  const nums = Object.values(values);
  const lo = Math.min(...nums);
  const hi = Math.max(...nums);
  const step = (v: number) =>
    nums.length < 2 || hi === lo ? 2 : Math.min(4, Math.floor(((v - lo) / (hi - lo)) * 5));
  const listed = Object.entries(values).sort((a, b) => b[1] - a[1]);

  return (
    <figure className="surface-data p-4">
      <div className="grid gap-4 md:grid-cols-[minmax(0,280px)_1fr] md:items-start">
        <svg
          viewBox={MAP_VIEWBOX}
          className="mx-auto h-auto w-full max-w-[280px]"
          role="img"
          aria-label={`${title}: ${listed.map(([d, v]) => `${districtName(d, lang)} ₹${v}`).join(", ")}`}
        >
          {DISTRICTS.map((d) => {
            const v = values[d.name];
            const i = v === undefined ? -1 : step(v);
            return (
              <path
                key={d.name}
                d={d.d}
                fill={i < 0 ? "var(--color-line)" : STEPS[i]}
                stroke="var(--color-surface-solid)"
                strokeWidth={1.2}
                strokeLinejoin="round"
              />
            );
          })}
          {DISTRICTS.filter((d) => values[d.name] !== undefined).map((d) => {
            const v = values[d.name] as number;
            return (
              <text
                key={d.name}
                x={d.cx}
                y={d.cy}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={13}
                fontWeight={700}
                fill="var(--color-ink)"
                stroke="var(--color-surface-solid)"
                strokeWidth={3.5}
                paintOrder="stroke"
                strokeLinejoin="round"
                className="tabular"
              >
                ₹{v}
              </text>
            );
          })}
        </svg>
        <div>
          <div className="flex items-center gap-2 text-[13px] text-ink-2" aria-hidden="true">
            <span className="tabular">₹{lo}</span>
            <span className="flex h-3 flex-1 overflow-hidden rounded-full">
              {STEPS.map((c) => (
                <span key={c} className="flex-1" style={{ background: c }} />
              ))}
            </span>
            <span className="tabular">₹{hi}</span>
          </div>
          <div className="mt-2 flex items-center gap-2 text-[13px] text-ink-2" aria-hidden="true">
            <span className="h-3 w-6 rounded-full" style={{ background: "var(--color-line)" }} />
            {none}
          </div>
          <ul className="tabular mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[15px]">
            {listed.map(([d, v]) => (
              <li key={d} className="flex justify-between gap-2">
                <span>{districtName(d, lang)}</span>
                <span className="font-semibold">₹{v}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <figcaption className="mt-3 text-[12px] text-ink-2">{MAP_ATTRIBUTION}</figcaption>
    </figure>
  );
}
