"use client";

// PWA: registers the service worker (production only) and offers "Add to home screen".
// Android/Chrome: the browser's beforeinstallprompt. iOS Safari has no prompt API: a one-line hint.
// Rendered as a fixed toast (no layout shift), dismissible, remembered per device.
import { useEffect, useState } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const KEY = "install-dismissed";

function dismissed(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function InstallPrompt({ label, iosHint, close }: { label: string; iosHint: string; close: string }) {
  const [evt, setEvt] = useState<BeforeInstallPromptEvent | null>(null);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    }
    if (dismissed()) return;
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    if (standalone) return;
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setEvt(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    const t = window.setTimeout(() => {
      if (/iphone|ipad|ipod/i.test(navigator.userAgent)) setIos(true);
    }, 4000);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.clearTimeout(t);
    };
  }, []);

  const hide = () => {
    setEvt(null);
    setIos(false);
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      /* private mode: just hide */
    }
  };

  if (!evt && !ios) return null;
  return (
    <div
      role="status"
      className="surface-glass fixed inset-x-3 bottom-[92px] z-30 mx-auto flex max-w-md items-center gap-3 p-3 md:bottom-6"
    >
      {evt ? (
        <button
          type="button"
          className="press min-h-11 flex-1 rounded-full bg-accent px-4 text-[15px] font-semibold text-accent-ink"
          onClick={async () => {
            await evt.prompt();
            await evt.userChoice.catch(() => undefined);
            hide();
          }}
        >
          {label}
        </button>
      ) : (
        <p className="flex-1 text-[14px]">{iosHint}</p>
      )}
      <button type="button" onClick={hide} className="press min-h-11 rounded-full px-3 text-[14px] font-semibold text-ink-2">
        {close}
      </button>
    </div>
  );
}
