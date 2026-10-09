import type { Crop } from "@/lib/crops";

/** Original line icons (24px grid, 1.75 stroke). Decorative: the crop name is always shown. */
const PATHS: Record<Crop, React.ReactNode> = {
  banana: (
    <>
      <path d="M5 7c1.2 6.4 6.3 10.6 13.6 10.2.6 0 .9-.6.5-1C14.6 13 10.4 9.6 8.6 4.7 8.3 4 7.4 3.8 6.9 4.3L5.5 5.6c-.4.4-.6.9-.5 1.4Z" />
      <path d="M8.2 5.1 7.4 3.4M18.9 16.9l1.4.8" />
    </>
  ),
  coconut: (
    <>
      <circle cx="12" cy="13" r="7" />
      <path d="M9.5 10.5h.01M12 9.5h.01M14.5 10.5h.01" strokeWidth="2.6" />
      <path d="M12 6c1-2 3-3 5.5-3M12 6c-1-2-3-3-5.5-3" />
    </>
  ),
  pepper: (
    <>
      <path d="M12 3v4M12 7c-3 0-5 2-5 4" />
      <circle cx="9" cy="13" r="2.2" />
      <circle cx="14.5" cy="12" r="2.2" />
      <circle cx="11.5" cy="17.5" r="2.2" />
      <circle cx="16.5" cy="17" r="2" />
    </>
  ),
  rubber: (
    <>
      <path d="M12 3.5s-5 5.8-5 9.5a5 5 0 0 0 10 0c0-3.7-5-9.5-5-9.5Z" />
      <path d="M10 14.5a2.2 2.2 0 0 0 2 1.9" />
    </>
  ),
  tapioca: (
    <>
      <path d="M8 4c-1 3 0 6 2 8 2.6 2.6 2.9 6.1 1.4 8.6M16.5 6c-1.5 2-1.3 4.6.4 6.6 1.5 1.8 1.6 4.2.5 6.1" />
      <path d="M6.5 13.5c1.6 0 3 .6 3.9 1.6M13.4 9.2c1.3.4 2.4 1.2 3 2.3" />
    </>
  ),
};

export function CropIcon({ crop, className = "h-7 w-7" }: { crop: Crop; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[crop]}
    </svg>
  );
}
