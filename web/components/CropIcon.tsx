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
  arecanut: (
    <>
      <path d="M12 3c-.6 1.6-.3 3 .8 4" />
      <ellipse cx="12" cy="14" rx="5" ry="6.5" />
      <path d="M9.6 11.5c.8-1.2 2.3-1.8 3.8-1.3" />
    </>
  ),
  coffee: (
    <>
      <ellipse cx="12" cy="12" rx="5.6" ry="7.6" transform="rotate(28 12 12)" />
      <path d="M8.6 17.4c2.4-1.7 3.2-3.9 2.6-6.1-.5-1.8.3-3.5 2.2-4.8" />
    </>
  ),
  ginger: (
    <>
      <path d="M5 15c0-2.5 1.8-4 4-4h1.5c.4-2 1.8-3.5 3.6-3.5 1.6 0 2.4 1.2 2.4 2.5" />
      <path d="M16.5 10c1.6.3 2.5 1.5 2.5 3 0 2.2-2 3.5-4.5 3.5H8c-1.7 0-3-.7-3-1.5" />
      <path d="M10.5 11v5.5M14 9.5v1" />
    </>
  ),
  palayankodan: (
    <>
      <path d="M6 8c.9 5.4 5.2 9 11.4 8.7.5 0 .7-.5.4-.8C14 13.6 10.6 10.8 9.1 6.7" />
      <path d="M8 6.2 7.3 4.6" />
      <path d="M9.3 4.3c1.3 1.9 3.2 3.4 5.5 4.2" />
    </>
  ),
  poovan: (
    <>
      <path d="M7 6.5c.3 6 4.5 10.6 11 10.8" />
      <path d="M7 6.5c2.6 4.6 6.4 7.7 11 8.6.6.1.8.8.3 1.2" />
      <path d="M7 6.5 6 4.6" />
    </>
  ),
  tomato: (
    <>
      <path d="M12 7.5c4.4 0 7.5 2.7 7.5 6.3S16.4 20 12 20s-7.5-2.6-7.5-6.2S7.6 7.5 12 7.5Z" />
      <path d="M12 7.5V4.5M9 6.2l3 1.3 3-1.3M12 7.5l-2.2 2.1M12 7.5l2.2 2.1" />
    </>
  ),
  onion: (
    <>
      <path d="M12 4c.2 2 1.4 3 3 4.2 2.4 1.7 4 3.6 4 6.3 0 3.2-3 5.5-7 5.5s-7-2.3-7-5.5c0-2.7 1.6-4.6 4-6.3C10.6 7 11.8 6 12 4Z" />
      <path d="M12 8.5c-1.6 2.3-1.6 8.7 0 11" />
      <path d="M10.5 21h3" />
    </>
  ),
  small_onion: (
    <>
      <path d="M9 7.5c.1 1.3.9 2 1.9 2.8 1.5 1.1 2.6 2.4 2.6 4.2 0 2.1-2 3.6-4.5 3.6S4.5 16.6 4.5 14.5c0-1.8 1.1-3.1 2.6-4.2 1-.8 1.8-1.5 1.9-2.8Z" />
      <path d="M15.5 9c.1 1 .7 1.6 1.4 2.2 1.1.8 1.9 1.8 1.9 3.1 0 1.6-1.5 2.7-3.3 2.7-.8 0-1.5-.2-2-.5" />
    </>
  ),
  green_chilli: (
    <>
      <path d="M8.5 7.5c-1.4 4.6-.4 9.6 4.2 12 .9.4 1.4-.6.9-1.3-2.6-3.5-3.2-7.1-2.4-10.4" />
      <path d="M8.5 7.5c.9-.9 2-1 3.2-.3M10 7 9.4 4.5c.6-.6 1.6-.5 2.4.2" />
    </>
  ),
  bitter_gourd: (
    <>
      <path d="M7 5.5c-1.7 3.6-.4 9.6 3.8 13 1.6 1.3 3.4 1.6 5 1 .9-.4.9-1.7.2-2.3-3.6-3.4-5.4-7.5-6-11.2" />
      <path d="M7 5.5 6 3.5M9 9.5l1.2-.6M10 13l1.3-.5M12.2 16.2l1.2-.6" />
    </>
  ),
  drumstick: (
    <>
      <path d="M6 4.5c3.8 4.5 7.8 9.6 12.5 15" />
      <path d="M8.3 6.9l-1 1.4M11.2 10.3l-1 1.4M14.1 13.7l-1 1.4M17 17.1l-1 1.4" />
    </>
  ),
  cucumber: (
    <>
      <rect x="3.5" y="9" width="17" height="6.5" rx="3.25" transform="rotate(-25 12 12.25)" />
      <path d="M8 13.5h.01M11 12h.01M14 10.5h.01M10 15h.01M13 13.5h.01" strokeWidth="2.2" />
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
