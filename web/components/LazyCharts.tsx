"use client";

// Recharts is the heaviest client bundle. It is fetched and rendered only after the page has
// painted and the browser is idle, and only once a chart is near the viewport: loading it during
// hydration held back the first paint by ~1-2 s on mobile (Lighthouse LCP).
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type ComponentProps, type ComponentType } from "react";

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

function whenVisible<P extends object>(Inner: ComponentType<P>, h: string) {
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
              setShow(true);
              io?.disconnect();
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
    return <div ref={ref}>{show ? <Inner {...props} /> : <Placeholder h={h} />}</div>;
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

export const PriceChart = whenVisible<ComponentProps<typeof PriceChartLazy>>(PriceChartLazy, "h-64");
export const TrendChart = whenVisible<ComponentProps<typeof TrendChartLazy>>(TrendChartLazy, "h-56");
