"""Weekly drift report (Evidently) + escalation.

* Feature drift (INFORMATIONAL): reference = the 90 days before the current window, current =
  the last 14 days, on the h=7 feature rows of all modelled series -- only stationary / relative
  features (lags relative to the last price, pct changes, CVs, spread, arrival ratios). Price
  levels, calendar, weather and data-coverage inputs drift by construction for a seasonal series,
  so they are left out. Share >= 50 % is flagged on the dashboard and in the weekly summary; it
  never alerts.
* Target drift: weekly price change log(p_t / p_{t-7}) per series, same windows (K-S test).
* HTML -> GitHub Release `reports-<date>` (not the repo, not Neon); summary -> drift_reports.
* Escalation (Telegram admin + GitHub issue) is on performance only:
  champion live 28-day MAPE (h=7, all crops) > 1.5x its backtest MAPE on each of the last 7 days,
  OR live p10-p90 coverage (h=7, all crops, last 28 days) outside 70-90 % once 28 days of matured
  forecasts exist, OR target drift with K-S p < 0.01.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from cropcast.features.build import NUMERIC_FEATURES, build_features
from cropcast.features.series import SERIES_KEY, Series
from cropcast.features.snapshot import Snapshot

log = logging.getLogger(__name__)

REF_DAYS = 90
CUR_DAYS = 14
FEATURE_DRIFT_INFO = 0.50  # informational flag only
MAPE_RATIO_ALERT = 1.5
MAPE_RATIO_DAYS = 7
COVERAGE_BAND = (70.0, 90.0)  # % of actuals inside p10-p90 (nominal 80 %)
COVERAGE_WINDOW_DAYS = 28
TARGET_P_ALERT = 0.01


def is_stationary(feature: str) -> bool:
    """Relative / scale-free features: comparable across a seasonal price level."""
    return (
        feature.endswith("_rel")
        or feature.startswith(("pct_change", "roll_cv"))
        or feature == "spread"
        or ("arrivals" in feature and "ratio" in feature)
    )


DRIFT_FEATURES = [c for c in NUMERIC_FEATURES if is_stationary(c)]


@dataclass
class DriftResult:
    report_date: date
    ref_start: date
    ref_end: date
    cur_start: date
    cur_end: date
    n_features: int
    n_drifted: int
    drift_share: float
    target_drift: bool
    target_p_value: float | None
    drifted: list[str] = field(default_factory=list)
    html_path: Path | None = None


def windows(last: date) -> tuple[date, date, date, date]:
    cur_end = last
    cur_start = last - timedelta(days=CUR_DAYS - 1)
    ref_end = cur_start - timedelta(days=1)
    ref_start = ref_end - timedelta(days=REF_DAYS - 1)
    return ref_start, ref_end, cur_start, cur_end


def weekly_changes(prices: pd.DataFrame) -> pd.DataFrame:
    """log(p_t / p_{t-7}) per series and day (prices carried forward <= 3 days)."""
    out = []
    for key, g in prices.groupby(SERIES_KEY):
        s = g.set_index(pd.to_datetime(g["date"]))["modal_price"].astype(float).sort_index()
        s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D")).ffill(limit=3)
        chg = pd.Series(np.log(s / s.shift(7)), index=s.index).dropna()
        frame = chg.rename("weekly_change").rename_axis("date").reset_index()
        out.append(frame.assign(commodity=str(key[0])))
    return pd.concat(out, ignore_index=True)


def _parse(snapshot_dict: dict[str, Any]) -> tuple[int, float, list[str], dict[str, Any]]:
    count, share, drifted, per_col = 0, 0.0, [], {}
    for m in snapshot_dict.get("metrics", []):
        cfg = m.get("config", {})
        kind = str(cfg.get("type", ""))
        if kind.endswith("DriftedColumnsCount"):
            count, share = int(m["value"]["count"]), float(m["value"]["share"])
        elif kind.endswith("ValueDrift"):
            col, value, thr = (
                cfg.get("column"),
                float(m["value"]),
                float(cfg.get("threshold", 0.05)),
            )
            method = str(cfg.get("method", ""))
            is_p = "p_value" in method or method in ("ks", "chisquare", "z")
            is_drift = value < thr if is_p else value >= thr
            per_col[str(col)] = {
                "method": method,
                "value": value,
                "threshold": thr,
                "drift": is_drift,
            }
            if is_drift:
                drifted.append(str(col))
    return count, share, sorted(drifted), per_col


def compute(
    snap: Snapshot, series: list[Series], out_dir: Path
) -> tuple[DriftResult, dict[str, Any]]:
    from evidently import Report
    from evidently.metrics import ValueDrift
    from evidently.presets import DataDriftPreset

    last = snap.last_date
    ref_start, ref_end, cur_start, cur_end = windows(last)
    f = build_features(snap.prices, snap.weather, last, 7, series)
    od = pd.to_datetime(f["origin_date"]).dt.date
    ref = f[(od >= ref_start) & (od <= ref_end)][DRIFT_FEATURES]
    cur = f[(od >= cur_start) & (od <= cur_end)][DRIFT_FEATURES]
    # Constant columns (e.g. a festival flag with no festival in either window) carry no drift.
    cols = [c for c in DRIFT_FEATURES if ref[c].nunique() > 1 or cur[c].nunique() > 1]
    feat = Report([DataDriftPreset(columns=cols)]).run(
        current_data=cur[cols], reference_data=ref[cols]
    )
    n_drifted, share, drifted, per_col = _parse(feat.dict())

    wc = weekly_changes(snap.prices)
    wd = pd.to_datetime(wc["date"]).dt.date
    tref, tcur = wc[(wd >= ref_start) & (wd <= ref_end)], wc[(wd >= cur_start) & (wd <= cur_end)]
    tgt = Report([ValueDrift(column="weekly_change", method="ks")]).run(
        current_data=tcur[["weekly_change"]], reference_data=tref[["weekly_change"]]
    )
    _, _, tdrift, tcol = _parse(tgt.dict())
    p_value = tcol.get("weekly_change", {}).get("value")

    out_dir.mkdir(parents=True, exist_ok=True)
    html = out_dir / f"drift_{last}.html"
    feat.save_html(str(html))
    tgt.save_html(str(out_dir / f"target_drift_{last}.html"))
    result = DriftResult(
        report_date=last,
        ref_start=ref_start,
        ref_end=ref_end,
        cur_start=cur_start,
        cur_end=cur_end,
        n_features=len(cols),
        n_drifted=n_drifted,
        drift_share=share,
        target_drift="weekly_change" in tdrift,
        target_p_value=p_value,
        drifted=drifted,
        html_path=html,
    )
    details = {"columns": per_col, "target": tcol, "ref_rows": len(ref), "cur_rows": len(cur)}
    return result, details


def mape_ratio_streak(engine: Engine, horizon: int = 7) -> tuple[int, float | None]:
    """Consecutive most-recent days on which live champion MAPE > 1.5x backtest MAPE."""
    with engine.connect() as conn:
        backtest = conn.execute(
            text(
                "SELECT value FROM model_metrics WHERE split = 'backtest' AND model_name = 'naive' "
                "AND commodity = 'all' AND horizon = :h AND metric = 'mape' "
                "ORDER BY computed_at DESC LIMIT 1"
            ),
            {"h": horizon},
        ).scalar()
        daily = conn.execute(
            text(
                "SELECT DISTINCT ON (computed_at::date) computed_at::date AS d, value "
                "FROM model_metrics WHERE split = 'live' AND model_name = 'champion' "
                "AND commodity = 'all' AND horizon = :h AND metric = 'mape_28d' "
                "ORDER BY computed_at::date DESC, computed_at DESC LIMIT 30"
            ),
            {"h": horizon},
        ).all()
    if backtest is None or not daily:
        return 0, None
    streak = 0
    for _, value in daily:
        if float(value) > MAPE_RATIO_ALERT * float(backtest):
            streak += 1
        else:
            break
    return streak, float(backtest)


def live_coverage(engine: Engine, horizon: int = 7) -> tuple[float | None, bool]:
    """Latest live p10-p90 coverage (%) and whether a full 28-day window of matured forecasts
    exists (a live coverage row computed >= 27 days ago); judged only when the window is full."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT value, (SELECT min(computed_at) FROM model_metrics WHERE split = 'live' "
                "AND model_name = 'champion' AND commodity = 'all' AND horizon = :h "
                "AND metric = 'coverage_80_28d') <= now() - make_interval(days => :w) AS full "
                "FROM model_metrics WHERE split = 'live' AND model_name = 'champion' "
                "AND commodity = 'all' AND horizon = :h AND metric = 'coverage_80_28d' "
                "ORDER BY computed_at DESC LIMIT 1"
            ),
            {"h": horizon, "w": COVERAGE_WINDOW_DAYS - 1},
        ).first()
    if row is None:
        return None, False
    return float(row[0]), bool(row[1])


def escalation_reasons(
    result: DriftResult,
    streak: int,
    backtest: float | None,
    coverage: float | None,
    coverage_full: bool,
) -> list[str]:
    """Performance-based escalation; feature drift never escalates."""
    reasons = []
    if streak >= MAPE_RATIO_DAYS and backtest is not None:
        reasons.append(
            f"champion live 28-day MAPE > {MAPE_RATIO_ALERT}x backtest ({backtest:.2f} %) "
            f"for {streak} consecutive days"
        )
    lo, hi = COVERAGE_BAND
    if coverage is not None and coverage_full and not lo <= coverage <= hi:
        reasons.append(f"p10-p90 coverage {coverage:.1f} % outside {lo:.0f}-{hi:.0f} % (28 days)")
    if result.target_p_value is not None and result.target_p_value < TARGET_P_ALERT:
        reasons.append(
            f"weekly price-change distribution shifted (K-S p = {result.target_p_value:.4f} "
            f"< {TARGET_P_ALERT})"
        )
    return reasons


def upload_html(result: DriftResult, files: list[Path]) -> str | None:
    """Attach the HTML reports to GitHub Release reports-<date>; return the asset URL."""
    if shutil.which("gh") is None:
        log.warning("gh not available: drift HTML not uploaded")
        return None
    tag = f"reports-{result.report_date}"
    notes = (
        f"Evidently drift report: reference {result.ref_start}..{result.ref_end}, "
        f"current {result.cur_start}..{result.cur_end}. "
        f"Stationary-feature drift (informational): {result.n_drifted}/{result.n_features} "
        f"({result.drift_share:.0%}"
        f"{', flagged >= 50 %' if result.drift_share >= FEATURE_DRIFT_INFO else ''}). "
        f"Weekly price-change K-S p = {result.target_p_value}."
    )
    exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
    if exists:
        subprocess.run(["gh", "release", "upload", tag, *map(str, files), "--clobber"], check=True)
    else:
        subprocess.run(
            ["gh", "release", "create", tag, *map(str, files), "--title", tag, "--notes", notes],
            check=True,
        )
    repo = subprocess.run(
        ["gh", "repo", "view", "--json", "url", "-q", ".url"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return f"{repo}/releases/download/{tag}/{files[0].name}"


def open_issue(title: str, body: str) -> None:
    """One open 'drift' issue at a time: comment on it if it exists, else open one."""
    if shutil.which("gh") is None:
        return
    subprocess.run(
        [
            "gh",
            "label",
            "create",
            "drift",
            "--color",
            "D93F0B",
            "--force",
            "--description",
            "automated drift / accuracy escalation",
        ],
        capture_output=True,
        check=False,
    )
    found = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--label",
            "drift",
            "--state",
            "open",
            "--json",
            "number",
            "-q",
            ".[0].number",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if found:
        comment = "\n\n".join([f"**{title}**", body])
        subprocess.run(["gh", "issue", "comment", found, "--body", comment], check=False)
    else:
        subprocess.run(
            ["gh", "issue", "create", "--title", title, "--body", body, "--label", "drift"],
            check=False,
        )


def store(
    engine: Engine,
    r: DriftResult,
    streak: int,
    escalated: bool,
    url: str | None,
    details: dict[str, Any],
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO drift_reports (report_date, ref_start, ref_end, cur_start, cur_end,
                n_features, n_drifted, drift_share, target_drift, target_p_value,
                mape_ratio_days, escalated, html_url, details)
            VALUES (:rd, :rs, :re, :cs, :ce, :nf, :nd, :sh, :td, :tp, :mr, :esc, :url,
                    CAST(:det AS JSONB))
            ON CONFLICT (report_date) DO UPDATE SET n_features = EXCLUDED.n_features,
                n_drifted = EXCLUDED.n_drifted, drift_share = EXCLUDED.drift_share,
                target_drift = EXCLUDED.target_drift, target_p_value = EXCLUDED.target_p_value,
                mape_ratio_days = EXCLUDED.mape_ratio_days, escalated = EXCLUDED.escalated,
                html_url = EXCLUDED.html_url, details = EXCLUDED.details, created_at = now()
            """),
            {
                "rd": r.report_date,
                "rs": r.ref_start,
                "re": r.ref_end,
                "cs": r.cur_start,
                "ce": r.cur_end,
                "nf": r.n_features,
                "nd": r.n_drifted,
                "sh": r.drift_share,
                "td": r.target_drift,
                "tp": r.target_p_value,
                "mr": streak,
                "esc": escalated,
                "url": url,
                "det": json.dumps({**details, "drifted": r.drifted}, default=str),
            },
        )


def run_weekly(
    engine: Engine, snap: Snapshot, series: list[Series], dry_run: bool, notify_admin: Any
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        result, details = compute(snap, series, Path(tmp))
        streak, backtest = mape_ratio_streak(engine)
        coverage, coverage_full = live_coverage(engine)
        reasons = escalation_reasons(result, streak, backtest, coverage, coverage_full)
        feature_flag = result.drift_share >= FEATURE_DRIFT_INFO
        details = {
            **details,
            "feature_drift_flag": feature_flag,
            "coverage_28d": coverage,
            "coverage_window_full": coverage_full,
            "escalation_reasons": reasons,
        }
        log.info(
            "weekly drift summary",
            extra={
                "feature_drift_share": round(result.drift_share, 3),
                "feature_drift_flag": feature_flag,
                "target_p": result.target_p_value,
                "coverage_28d": coverage,
                "mape_ratio_days": streak,
                "escalated": bool(reasons),
            },
        )
        url = None
        if not dry_run:
            files = [result.html_path] if result.html_path else []
            files += sorted(Path(tmp).glob("target_drift_*.html"))
            url = upload_html(result, files) if files else None
            store(engine, result, streak, bool(reasons), url, details)
            if reasons:
                msg = (
                    f"cropcast drift escalation {result.report_date}: "
                    + "; ".join(reasons)
                    + (f"\nreport: {url}" if url else "")
                )
                notify_admin(msg)
                open_issue(f"Drift escalation {result.report_date}", msg)
    return {
        "drift_share": round(result.drift_share, 3),
        "feature_drift_flag": result.drift_share >= FEATURE_DRIFT_INFO,
        "coverage_28d": coverage,
        "reasons": reasons,
        "n_drifted": result.n_drifted,
        "n_features": result.n_features,
        "drifted": result.drifted,
        "target_drift": result.target_drift,
        "target_p": result.target_p_value,
        "mape_ratio_days": streak,
        "escalated": bool(reasons),
        "html_url": url,
    }
