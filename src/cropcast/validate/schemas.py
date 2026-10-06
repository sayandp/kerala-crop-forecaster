"""Data contracts (Pandera). Bad rows are quarantined with a reason, never silently dropped.

Contract for prices_raw (see CLAUDE.md "Data rules"):
  * modal_price > 0 always; min_price <= modal_price <= max_price for the bounds that are
    present (min/max are NULL when a market reports only the modal price)
  * no future dates, no missing key fields
  * state == "Kerala", commodity is a canonical target crop
  * (date, market, commodity, variety) is unique — the first occurrence is kept,
    later duplicates are rejected.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

import numpy as np
import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from cropcast.config import settings

log = logging.getLogger(__name__)

KEY = ["date", "market", "commodity", "variety"]


class RejectRateExceeded(RuntimeError):
    """Raised when too large a share of a batch fails the contract."""


def price_schema(
    today: date, commodities: list[str] | None = None, check_unique: bool = True
) -> pa.DataFrameSchema:
    allowed = commodities if commodities is not None else settings.target_commodities
    non_empty = pa.Check.str_length(min_value=1)
    return pa.DataFrameSchema(
        {
            "date": pa.Column(
                "datetime64[ns]",
                pa.Check.le(pd.Timestamp(today), error="future_date"),
                nullable=False,
            ),
            "state": pa.Column(str, pa.Check.eq(settings.state, error="state_not_kerala")),
            "district": pa.Column(str, nullable=True),
            "market": pa.Column(str, non_empty, nullable=False),
            "commodity": pa.Column(str, pa.Check.isin(allowed, error="unknown_commodity")),
            "variety": pa.Column(str, non_empty, nullable=False),
            # NULL bounds = the market reported only the modal price.
            "min_price": pa.Column(
                float, pa.Check.ge(0, error="negative_min_price"), nullable=True
            ),
            "max_price": pa.Column(float, nullable=True),
            "modal_price": pa.Column(float, pa.Check.gt(0, error="modal_price_not_positive")),
            "arrivals_tonnes": pa.Column(
                float, pa.Check.ge(0, error="negative_arrivals"), nullable=True
            ),
            "source": pa.Column(str, nullable=False),
        },
        checks=[
            pa.Check(
                # A bound is only checked when present (both present => min <= modal <= max).
                lambda d: (
                    (d["min_price"].isna() | (d["min_price"] <= d["modal_price"]))
                    & (d["max_price"].isna() | (d["modal_price"] <= d["max_price"]))
                ),
                error="min_le_modal_le_max",
            ),
        ],
        unique=KEY if check_unique else None,
        report_duplicates="exclude_first",
        strict=False,
        coerce=False,
    )


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").astype("datetime64[ns]")
    if "arrivals_tonnes" not in out.columns:
        out["arrivals_tonnes"] = np.nan
    for col in ("min_price", "max_price", "modal_price", "arrivals_tonnes"):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype(float)
    for col in ("state", "district", "market", "commodity", "variety", "source"):
        out[col] = out[col].astype(object).where(out[col].notna(), None)
        out[col] = out[col].map(lambda v: v if v is None else str(v)).astype(object)
    return out


def _reason(row: pd.Series) -> str:
    check = str(row["check"])
    column = row["column"]
    if check in {"not_nullable", "column_in_dataframe"}:
        check = "missing_value"
    if check.startswith("field_uniqueness") or check == "multiple_fields_uniqueness":
        return "duplicate_key"
    if row.get("schema_context") == "DataFrameSchema" or column is None or pd.isna(column):
        return check  # frame-wide check: pandera reports it once per column
    return f"{column}:{check}"


def validate(
    df: pd.DataFrame,
    today: date | None = None,
    commodities: list[str] | None = None,
    check_unique: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a normalized batch into (good_df, rejected_df). rejected_df has a `reason` column."""
    from cropcast.ingest.agmarknet import today_ist

    data = _prepare(df)
    schema = price_schema(today or today_ist(), commodities, check_unique)
    try:
        schema.validate(data, lazy=True)
        good = data
        rejected = data.iloc[0:0].assign(reason=pd.Series(dtype=str))
    except SchemaErrors as err:
        fc = err.failure_cases
        if fc["index"].isna().any():
            # Schema-level failure (missing column / wrong dtype): a code bug, not bad data.
            schema_level = fc.loc[fc["index"].isna(), ["column", "check"]].to_dict("records")
            raise RuntimeError(f"price frame does not match the contract: {schema_level}") from err
        reasons: dict[int, set[str]] = defaultdict(set)
        for _, row in fc.iterrows():
            reasons[int(row["index"])].add(_reason(row))
        bad_idx = sorted(reasons)
        rejected = data.loc[bad_idx].copy()
        rejected["reason"] = [";".join(sorted(reasons[i])) for i in bad_idx]
        good = data.drop(index=bad_idx)
    good = good.assign(date=good["date"].dt.date).reset_index(drop=True)
    rejected = rejected.reset_index(drop=True)
    if not rejected.empty:
        log.warning(
            "rows failed contract",
            extra={
                "rejected": len(rejected),
                "reasons": rejected["reason"].value_counts().to_dict(),
            },
        )
    return good, rejected


def check_reject_rate(total: int, rejected: int, limit: float | None = None) -> float:
    """Raise RejectRateExceeded if rejected/total > limit (default settings.max_reject_fraction)."""
    limit = settings.max_reject_fraction if limit is None else limit
    rate = rejected / total if total else 0.0
    if rate > limit:
        raise RejectRateExceeded(
            f"{rejected}/{total} rows ({rate:.1%}) failed validation (limit {limit:.0%})"
        )
    return rate
