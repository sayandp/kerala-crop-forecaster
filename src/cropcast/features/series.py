"""The modelled series list (config/series.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from cropcast.config import PROJECT_ROOT

SERIES_PATH = PROJECT_ROOT / "config" / "series.yaml"
SERIES_KEY = ["commodity", "market", "variety"]


@dataclass(frozen=True)
class Series:
    commodity: str
    market: str
    variety: str

    @property
    def label(self) -> str:
        return f"{self.commodity} · {self.market} · {self.variety}"


def load_series(path: Path = SERIES_PATH) -> list[Series]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = [Series(str(s["commodity"]), str(s["market"]), str(s["variety"])) for s in data["series"]]
    if len(set(out)) != len(out):
        raise ValueError(f"duplicate series in {path}")
    return out


def series_frame(series: list[Series]) -> pd.DataFrame:
    return pd.DataFrame([s.__dict__ for s in series], columns=SERIES_KEY)
