"use client";

// Bottom sheet on the native <dialog>: focus trap, Esc to close and inert background for free.
// The sheet is the only optional (3rd) blurred layer.
import { useRef, type ReactNode } from "react";

export function Sheet({
  label,
  title,
  closeLabel,
  children,
}: {
  label: ReactNode;
  title: string;
  closeLabel: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button
        type="button"
        onClick={() => ref.current?.showModal()}
        aria-haspopup="dialog"
        className="press surface-glass inline-flex min-h-11 items-center gap-2 !rounded-full px-4 text-[15px] font-semibold"
      >
        {label}
      </button>
      <dialog
        ref={ref}
        className="sheet glass glass-thick"
        aria-label={title}
        onClick={(e) => {
          if (e.target === ref.current) ref.current?.close(); // tap on the backdrop
        }}
      >
        <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-2">
          <h2 className="text-lg font-bold">{title}</h2>
          <button
            type="button"
            onClick={() => ref.current?.close()}
            className="press min-h-11 rounded-full px-4 text-[15px] font-semibold text-accent"
          >
            {closeLabel}
          </button>
        </div>
        <div className="max-h-[65dvh] overflow-y-auto px-3 pb-[max(env(safe-area-inset-bottom),16px)]">{children}</div>
      </dialog>
    </>
  );
}
