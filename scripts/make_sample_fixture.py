"""Freeze tests/fixtures/sample_prices.parquet from REAL backfilled prices_raw data.

Picks, per crop, the series (market, variety) with the most observed days in the last
two full years, plus the runner-up for banana (the main crop). Run once after the
backfill; the output is committed and must not change afterwards (model-quality tests
depend on it being frozen).

    uv run python scripts/make_sample_fixture.py --end 2026-09-30
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from cropcast.db import get_engine

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "sample_prices.parquet"
PER_CROP = {"banana": 2, "coconut": 1, "rubber": 1, "pepper": 1, "tapioca": 1}
# The varieties the project actually targets; used when they have >= 80% of the best count.
PREFERRED = {"banana": "Nendran", "rubber": "RSS-4"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--days", type=int, default=730)
    args = p.parse_args()
    start = args.end - timedelta(days=args.days - 1)

    df = pd.read_sql(
        text(
            "SELECT date, district, market, commodity, variety, min_price, max_price, "
            "modal_price FROM prices_raw WHERE date BETWEEN :s AND :e"
        ),
        get_engine(),
        params={"s": start, "e": args.end},
        parse_dates=["date"],
    )
    counts = (
        df.groupby(["commodity", "market", "variety"])["date"]
        .nunique()
        .rename("n")
        .reset_index()
        .sort_values("n", ascending=False)
    )
    chosen = []
    for crop, k in PER_CROP.items():
        cands = counts[counts.commodity == crop]
        pref = cands[cands.variety == PREFERRED.get(crop, "")]
        if len(pref) and pref.n.iloc[0] >= 0.8 * cands.n.iloc[0]:
            cands = pref
        chosen.append(cands.head(k))
    picks = pd.concat(chosen, ignore_index=True)
    sample = df.merge(
        picks[["commodity", "market", "variety"]], on=["commodity", "market", "variety"]
    )
    for col in ("min_price", "max_price", "modal_price"):
        sample[col] = sample[col].astype(float)
    sample = sample.sort_values(["commodity", "market", "variety", "date"]).reset_index(drop=True)
    sample.to_parquet(OUT, index=False)
    print(picks.to_string(index=False))
    print(f"wrote {OUT} rows={len(sample)} {start}..{args.end}")


if __name__ == "__main__":
    main()
