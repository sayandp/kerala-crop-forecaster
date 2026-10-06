"""prices_clean: aliases applied + same-day duplicate reports aggregated. Pure functions.

Inputs are prices_raw rows plus the same-day *duplicate* reports that the contract
quarantined in prices_rejected (reason duplicate_key: e.g. two grades of Nendran at one
market on one day). Both are needed to aggregate a day honestly.
"""

from __future__ import annotations

import pandas as pd

from cropcast.clean.aliases import apply_aliases
from cropcast.ingest.mappings import apply_price_conventions
from cropcast.validate.schemas import validate

KEY = ["commodity", "market", "variety", "date"]
INPUT_COLUMNS = [*KEY, "min_price", "max_price", "modal_price", "source"]
CLEAN_COLUMNS = [*KEY, "modal_price", "min_price", "max_price", "n_reports", "sources"]


def eligible_duplicates(rejected: pd.DataFrame) -> pd.DataFrame:
    """Quarantined rows whose only fault was being a same-day duplicate report.

    The daily lookback re-quarantines the same report on several runs, so exact repeats
    (key + prices + source) are collapsed to one.
    """
    if rejected.empty:
        return pd.DataFrame(columns=INPUT_COLUMNS)
    dup = rejected[rejected["reason"].str.contains("duplicate_key", na=False)]
    dup = apply_price_conventions(dup)  # modal-only (0/0) duplicates are valid since 002
    good, _ = validate(dup, check_unique=False)
    return good.drop_duplicates(subset=INPUT_COLUMNS).loc[:, INPUT_COLUMNS]


def aggregate_same_day(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (commodity, market, variety, date): median modal, min/max envelope."""
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)
    work = df.assign(date=pd.to_datetime(df["date"]).dt.date)
    for col in ("modal_price", "min_price", "max_price"):
        work[col] = pd.to_numeric(work[col], errors="coerce").astype(float)
    g = work.groupby(KEY, sort=True, dropna=False)
    out = g.agg(
        modal_price=("modal_price", "median"),
        min_price=("min_price", "min"),  # NaN-skipping: NULL only if every report is modal-only
        max_price=("max_price", "max"),
        n_reports=("modal_price", "size"),
        sources=("source", lambda s: ",".join(sorted(set(map(str, s))))),
    ).reset_index()
    out["modal_price"] = out["modal_price"].round(2)
    return out.loc[:, CLEAN_COLUMNS]


def build_clean(raw: pd.DataFrame, duplicates: pd.DataFrame, aliases: pd.DataFrame) -> pd.DataFrame:
    frames = [f.loc[:, INPUT_COLUMNS] for f in (raw, duplicates) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=CLEAN_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    return aggregate_same_day(apply_aliases(combined, aliases))
