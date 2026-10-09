"use client";

// Recharts is the heaviest client bundle. It is fetched only after the first user interaction
// (or 10 s) and only once a chart is near the viewport; loading it during hydration held back
// the first paint by ~1-2 s on mobile and added ~170 ms TBT on short pages.
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type ComponentProps, type ComponentType, type ReactNode } from "react";
import { Sparkline } from "@/components/Sparkline";

function Placeholder({ h }: { h: string }) {
  return <div className={`${h} w-full animate-pulse rounded-[18px] bg-line`} />;
}

/**
 * Run `fn` after the user's first interaction (pointer, touch, scroll, key), or 10 s after load.
 * Until then the server-rendered SVG stand-in shows the data; Recharts (the heaviest bundle)
 * never competes with first paint or the main thread during load.
 */
let interacted: Promise<void> | null = null;
function firstInteraction(): Promise<void> {
  if (interacted) return interacted;
  interacted = new Promise((resolve) => {
    const events = ["pointerdown", "pointermove", "touchstart", "scroll", "keydown", "wheel"] as const;
    const done = () => {
      events.forEach((e) => window.removeEventListener(e, done));
      resolve();
    };
    events.forEach((e) => window.addEventListener(e, done, { once: true, passive: true }));
    const fallback = () => window.setTimeout(done, 10_000);
    if (document.readyState === "complete") fallback();
    else window.addEventListener("load", fallback, { once: true });
  });
  return interacted;
}

function afterInteraction(fn: () => void): () => void {
  let cancelled = false;
  void firstInteraction().then(() => {
    if (!cancelled) fn();
  });
  return () => {
    cancelled = true;
  };
}

const loadCharts = () => import("@/components/Charts");

function whenVisible<P extends object>(Inner: ComponentType<P>, fallback: (props: P) => ReactNode) {
  return function VisibleChart(props: P) {
    const ref = useRef<HTMLDivElement>(null);
    const [show, setShow] = useState(false);
    useEffect(() => {
      const el = ref.current;
      if (!el || typeof IntersectionObserver === "undefined") {
        setShow(true);
        return;
      }
      let io: IntersectionObserver | undefined;
      const observe = () => {
        io = new IntersectionObserver(
          (entries) => {
            if (entries.some((e) => e.isIntersecting)) {
              io?.disconnect();
              // Fetch Recharts first, then swap: the stand-in stays until the chart can render.
              void loadCharts().then(() => setShow(true));
            }
          },
          { rootMargin: "200px" },
        );
        io.observe(el);
      };
      const cancel = afterInteraction(observe);
      return () => {
        cancel();
        io?.disconnect();
      };
    }, []);
    return <div ref={ref}>{show ? <Inner {...props} /> : fallback(props)}</div>;
  };
}

const PriceChartLazy = dynamic(() => import("@/components/Charts").then((m) => m.PriceChart), {
  ssr: false,
  loading: () => <Placeholder h="h-64" />,
});

const TrendChartLazy = dynamic(() => import("@/components/Charts").then((m) => m.TrendChart), {
  ssr: false,
  loading: () => <Placeholder h="h-56" />,
});

const SeasonChartLazy = dynamic(() => import("@/components/Charts").then((m) => m.SeasonChart), {
  ssr: false,
  loading: () => <Placeholder h="h-72" />,
});

type PriceProps = ComponentProps<typeof PriceChartLazy>;
type SeasonProps = ComponentProps<typeof SeasonChartLazy>;
type TrendProps = ComponentProps<typeof TrendChartLazy>;

// The price chart is above the fold on the home page: its stand-in is a server-rendered SVG of the
// same data (no layout shift, real content before any JS); the trend charts sit lower and pulse.
export const PriceChart = whenVisible<PriceProps>(PriceChartLazy, (p) => <Sparkline data={p.data} />);
export const TrendChart = whenVisible<TrendProps>(TrendChartLazy, () => <Placeholder h="h-56" />);
export const SeasonChart = whenVisible<SeasonProps>(SeasonChartLazy, () => <Placeholder h="h-72" />);
