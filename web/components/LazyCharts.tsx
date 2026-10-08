"use client";

// Recharts is the heaviest client bundle. It is fetched and rendered only after the page has
// painted and the browser is idle, and only once a chart is near the viewport: loading it during
// hydration held back the first paint by ~1-2 s on mobile (Lighthouse LCP).
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type ComponentProps, type ComponentType, type ReactNode } from "react";
import { Sparkline } from "@/components/Sparkline";

function Placeholder({ h }: { h: string }) {
  return <div className={`${h} w-full animate-pulse rounded-xl bg-line/40`} />;
}

/** Run `fn` once the page has loaded, a frame has been painted and the main thread is idle. */
function afterFirstPaintIdle(fn: () => void): () => void {
  let cancelled = false;
  let idle: number | undefined;
  const run = () => {
    requestAnimationFrame(() =>
      setTimeout(() => {
        if (cancelled) return;
        if ("requestIdleCallback" in window) idle = window.requestIdleCallback(fn, { timeout: 2000 });
        else fn();
      }, 0),
    );
  };
  if (document.readyState === "complete") run();
  else window.addEventListener("load", run, { once: true });
  return () => {
    cancelled = true;
    window.removeEventListener("load", run);
    if (idle !== undefined) window.cancelIdleCallback(idle);
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
      const cancel = afterFirstPaintIdle(observe);
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

type PriceProps = ComponentProps<typeof PriceChartLazy>;
type TrendProps = ComponentProps<typeof TrendChartLazy>;

// The price chart is above the fold on the home page: its stand-in is a server-rendered SVG of the
// same data (no layout shift, real content before any JS); the trend charts sit lower and pulse.
export const PriceChart = whenVisible<PriceProps>(PriceChartLazy, (p) => <Sparkline data={p.data} />);
export const TrendChart = whenVisible<TrendProps>(TrendChartLazy, () => <Placeholder h="h-56" />);
