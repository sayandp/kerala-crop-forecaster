"use client";

import { useRouter } from "next/navigation";

export interface PickerOption {
  value: string;
  label: string;
}

/** Crop × market selector; navigates to the series page (each is statically rendered). */
export function SeriesPicker({
  label,
  options,
  current,
}: {
  label: string;
  options: PickerOption[];
  current: string;
}) {
  const router = useRouter();
  return (
    <label className="block text-sm">
      <span className="text-muted">{label}</span>
      <select
        className="mt-1 block w-full rounded-lg border border-line bg-paper px-3 py-3 text-base"
        value={current}
        onChange={(e) => router.push(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
