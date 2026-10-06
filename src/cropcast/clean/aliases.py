"""Variety aliases: guarded merges of labels that were renamed at the portal switch.

Pure functions (no I/O except reading the candidate YAML). See variety_aliases.yaml for the
rules; `evaluate_candidates` decides per market, `apply_aliases` relabels rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_CANDIDATES = Path(__file__).resolve().parents[1] / "ingest" / "variety_aliases.yaml"
ALIAS_COLUMNS = [
    "commodity",
    "market",
    "raw_variety",
    "canonical_variety",
    "valid_from",
    "valid_to",
    "guard_ratio",
]
DECISION_COLUMNS = [
    "commodity",
    "market",
    "raw_variety",
    "canonical_variety",
    "n_before",
    "n_after",
    "median_before",
    "median_after",
    "ratio",
    "decision",
]


@dataclass(frozen=True)
class AliasCandidate:
    commodity: str
    raw_variety: str
    canonical_variety: str


def load_candidates(path: Path = DEFAULT_CANDIDATES) -> list[AliasCandidate]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        AliasCandidate(str(c["commodity"]), str(c["raw_variety"]), str(c["canonical_variety"]))
        for c in data.get("switch_renames") or []
    ]


def evaluate_candidates(
    prices: pd.DataFrame,
    candidates: list[AliasCandidate],
    switch: date,
    tolerance: float,
    window_days: int,
    min_obs: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Decide, per (candidate, market), whether the rename is a true relabel.

    Accepted only if the raw label stops at the switch, the canonical label starts there,
    both sides have >= min_obs reports and the 30-day medians agree within `tolerance`.

    `prices` needs date, market, commodity, variety, modal_price and must cover at least
    [switch - window, switch + window). Returns (accepted aliases, all decisions).
    """
    df = prices.assign(date=pd.to_datetime(prices["date"]))
    sw = pd.Timestamp(switch)
    lo, hi = sw - pd.Timedelta(days=window_days), sw + pd.Timedelta(days=window_days)
    decisions: list[dict[str, object]] = []
    for cand in candidates:
        c = df[df["commodity"] == cand.commodity]
        raw = c[c["variety"] == cand.raw_variety]
        canon = c[c["variety"] == cand.canonical_variety]
        markets = sorted(set(raw.loc[(raw.date >= lo) & (raw.date < sw), "market"]))
        for market in markets:
            r, k = raw[raw.market == market], canon[canon.market == market]
            before = r[(r.date >= lo) & (r.date < sw)]["modal_price"]
            after = k[(k.date >= sw) & (k.date < hi)]["modal_price"]
            med_b = float(before.median()) if len(before) else float("nan")
            med_a = float(after.median()) if len(after) else float("nan")
            ratio = med_b / med_a - 1 if len(before) and len(after) else float("nan")
            # A label "lives" on a side of the switch only with >= min_obs reports there;
            # a few stray rows (late reports) do not make two products.
            raw_after = int(((r.date >= sw) & (r.date < hi)).sum())
            canon_before = int(((k.date >= lo) & (k.date < sw)).sum())
            if raw_after >= min_obs:
                decision = "rejected: raw label still reported after switch (two products)"
            elif canon_before >= min_obs:
                decision = "rejected: canonical label already reported before switch"
            elif len(before) < min_obs or len(after) < min_obs:
                decision = f"rejected: insufficient data (< {min_obs} obs per side)"
            elif abs(ratio) > tolerance:
                decision = f"rejected: price ratio {ratio:+.1%} outside ±{tolerance:.0%}"
            else:
                decision = "accepted"
            decisions.append(
                {
                    "commodity": cand.commodity,
                    "market": market,
                    "raw_variety": cand.raw_variety,
                    "canonical_variety": cand.canonical_variety,
                    "n_before": len(before),
                    "n_after": len(after),
                    "median_before": med_b,
                    "median_after": med_a,
                    "ratio": ratio,
                    "decision": decision,
                }
            )
    dec = pd.DataFrame(decisions, columns=DECISION_COLUMNS)
    ok = dec[dec["decision"] == "accepted"]
    accepted = pd.DataFrame(
        {
            "commodity": ok["commodity"],
            "market": ok["market"],
            "raw_variety": ok["raw_variety"],
            "canonical_variety": ok["canonical_variety"],
            "valid_from": None,
            "valid_to": switch - timedelta(days=1),
            "guard_ratio": ok["ratio"],
        },
        columns=ALIAS_COLUMNS,
    ).reset_index(drop=True)
    return accepted, dec


def apply_aliases(df: pd.DataFrame, aliases: pd.DataFrame) -> pd.DataFrame:
    """Relabel `variety` per alias rows (market NULL = all markets; date bounds inclusive)."""
    out = df.copy()
    if aliases.empty or out.empty:
        return out
    dates = pd.to_datetime(out["date"])
    starts = pd.to_datetime(aliases["valid_from"])
    ends = pd.to_datetime(aliases["valid_to"])
    for i in range(len(aliases)):
        a = aliases.iloc[i]
        mask = (out["commodity"] == a["commodity"]) & (out["variety"] == a["raw_variety"])
        if pd.notna(a["market"]):
            mask &= out["market"] == a["market"]
        if pd.notna(starts.iloc[i]):
            mask &= dates >= starts.iloc[i]
        if pd.notna(ends.iloc[i]):
            mask &= dates <= ends.iloc[i]
        out.loc[mask, "variety"] = a["canonical_variety"]
    return out
