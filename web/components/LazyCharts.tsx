"use client";

// Recharts is the heaviest client bundle. It is fetched and evaluated only when a chart scrolls
// near the viewport (charts sit below the fold on mobile), so it never competes with first paint.
import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type ComponentProps, type ComponentType } from "react";

function Placeholder({ h }: { h: string }) {
  return <div className={`${h} w-full animate-pulse rounded-xl bg-line/40`} />;
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
      const io = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) {
            setShow(true);
            io.disconnect();
          }
        },
        { rootMargin: "200px" },
      );
      io.observe(el);
      return () => io.disconnect();
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
