"""Unit sanity: modal prices must be plausible Rs./kg for the crop (config/units.yaml)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
import yaml

from cropcast.config import PROJECT_ROOT

UNITS_PATH = PROJECT_ROOT / "config" / "units.yaml"


@lru_cache(maxsize=1)
def bands() -> dict[str, dict[str, float]]:
    data: dict[str, Any] = yaml.safe_load(UNITS_PATH.read_text(encoding="utf-8"))
    return {
        k: {"min": float(v["min"]), "max": float(v["max"])}
        for k, v in data["bands_rs_per_kg"].items()
    }


def rs_per_kg(rs_per_quintal: pd.Series | float) -> Any:
    return rs_per_quintal / 100.0


def implausible(commodity: pd.Series, modal_rs_per_quintal: pd.Series) -> pd.Series:
    """True where the price is outside the crop's band (unknown crops are never flagged)."""
    b = bands()
    lo = commodity.map(lambda c: b.get(str(c), {}).get("min", -np.inf)).astype(float)
    hi = commodity.map(lambda c: b.get(str(c), {}).get("max", np.inf)).astype(float)
    kg = rs_per_kg(modal_rs_per_quintal.astype(float))
    out: pd.Series = (kg < lo) | (kg > hi)
    return out
