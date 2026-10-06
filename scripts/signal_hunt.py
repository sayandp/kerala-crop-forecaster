"""Phase 2.5 signal hunt. One subcommand per experiment; each logs one MLflow child run under
the parent "phase2.5-signal-hunt" and writes reports/phase2_5/<name>.{json,csv}.

    uv run python scripts/signal_hunt.py snapshot          # one DB read (Neon) -> parquet
    uv run python scripts/signal_hunt.py E0                 # Phase-2 LGBM (reference)
    uv run python scripts/signal_hunt.py E1 | E2 | E3 | E4a | E4b | E5
    uv run python scripts/signal_hunt.py report             # -> reports/phase2_5_signal_hunt.md

Yardstick: 52-fold walk-forward diagnostic at h=7 (p50). Decision rule in harness.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

from cropcast import db
from cropcast.experiments import harness as H
from cropcast.experiments.extra_features import (
    ARRIVAL_FEATURES,
    UPSTREAM_FEATURES,
    arrival_features,
    merge_extra,
    upstream_features,
    upstream_index,
)
from cropcast.features.build import FEATURE_COLUMNS, TARGET, build_features, festival_dates
from cropcast.features.series import SERIES_KEY
from cropcast.ingest.agmarknet import today_ist
from cropcast.ingest.mappings import market_districts
from cropcast.logging_setup import setup_logging
from cropcast.models.backtest import make_folds, run_backtest, split_fold
from cropcast.models.dm import dm_test
from cropcast.models.lgbm import DEFAULT_PARAMS, SEED, LGBMForecaster

log = logging.getLogger("cropcast.signal_hunt")

ASOF_FILE = H.results_dir() / "asof.txt"


def _asof() -> date:
    return date.fromisoformat(ASOF_FILE.read_text(encoding="utf-8").strip())


def _base(d: H.HuntData) -> pd.DataFrame:
    return build_features(d.prices, d.weather, d.last_date, H.HORIZON, d.series)


def _backtest(d: H.HuntData, feats: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    res = run_backtest(
        {H.HORIZON: feats},
        d.prices,
        d.last_date,
        n_folds=H.N_FOLDS,
        quantiles=(0.5,),
        feature_columns=cols,
    )
    return res.predictions


def _regression_experiment(
    name: str, desc: str, d: H.HuntData, feats: pd.DataFrame, cols: list[str], extra: dict
) -> pd.DataFrame:
    preds = _backtest(d, feats, cols)
    preds.to_parquet(H.results_dir() / f"{name}_predictions.parquet", index=False)
    sc = H.score(preds, "lgbm")
    allrow = sc[sc["crop"] == "all"].iloc[0]
    verdict = "WIN" if bool(allrow["wins"]) else "no win"
    crop_wins = sc[(sc["crop"] != "all") & sc["wins"]]["crop"].tolist()
    if crop_wins and verdict != "WIN":
        verdict = f"no win overall; wins for {', '.join(crop_wins)}"
    headline = {
        "mape_lgbm": allrow["mape_lgbm"],
        "mape_naive": allrow["mape_naive"],
        "rel_improvement_pct": allrow["rel_improvement_pct"],
        "dm_p": allrow["dm_p"],
    }
    H.log_experiment(
        name, desc, {"features": len(cols), **extra}, {"scores": sc}, headline, verdict
    )
    log.info("result", extra={"experiment": name, "verdict": verdict})
    print(sc.round(4).to_string(index=False))
    return preds


# --- experiments --------------------------------------------------------------------------


def cmd_snapshot() -> None:
    asof = today_ist()
    H.take(db.get_engine(), asof)
    ASOF_FILE.write_text(str(asof), encoding="utf-8")


def cmd_e0(d: H.HuntData) -> None:
    _regression_experiment(
        "E0_reference",
        "Phase-2 LightGBM (all Phase-2 features incl. market/variety categoricals), 20 series",
        d,
        _base(d),
        list(FEATURE_COLUMNS),
        {"series": len(d.series)},
    )


def cmd_e1(d: H.HuntData) -> None:
    end = pd.Timestamp(d.last_date) + pd.Timedelta(days=1)
    extra = arrival_features(d.prices, d.kerala_arrivals, end)
    feats = merge_extra(_base(d), extra, [*SERIES_KEY, "origin_date"])
    cov = feats[ARRIVAL_FEATURES].notna().mean().round(3).to_dict()
    _regression_experiment(
        "E1_arrivals",
        "E0 + arrivals: own lag 1/7, ratio to 28-day mean; Kerala commodity total lag 1, ratio",
        d,
        feats,
        [*FEATURE_COLUMNS, *ARRIVAL_FEATURES],
        {"coverage": json.dumps(cov)},
    )


def cmd_e2(d: H.HuntData) -> None:
    up = pd.read_parquet(H.settings.data_dir / "upstream" / "upstream_prices.parquet")
    idx = upstream_index(up)
    idx.to_parquet(H.results_dir() / "E2_upstream_index.parquet", index=False)
    extra = upstream_features(idx)
    feats = merge_extra(_base(d), extra, ["commodity", "origin_date"])
    cov = feats.groupby(feats["commodity"].astype(str))["up1_chg_7"].apply(
        lambda s: round(float(s.notna().mean()), 3)
    )
    _regression_experiment(
        "E2_upstream",
        "E0 + lagged 1/3/7-day change of upstream (TN/KA) median price index per crop",
        d,
        feats,
        [*FEATURE_COLUMNS, *UPSTREAM_FEATURES],
        {"coverage_up1": json.dumps(cov.to_dict()), "markets_per_index": 15},
    )


def cmd_e3(d: H.HuntData) -> None:
    cols = [c for c in FEATURE_COLUMNS if c not in ("market", "variety")]
    feats = _base(d)
    _regression_experiment(
        "E3_no_market_cat",
        "E0 without market/variety categoricals (commodity pooling + series-relative features)",
        d,
        feats,
        cols,
        {"dropped": "market,variety"},
    )
    # Where does importance go? Fit once on all data, with and without the categoricals.
    train = feats.dropna(subset=[TARGET])
    imp = {}
    for label, c in (("with_market", list(FEATURE_COLUMNS)), ("without_market", cols)):
        m = LGBMForecaster(H.HORIZON, quantiles=(0.5,), features=c).fit(train)
        g = m.feature_importance()
        imp[label] = (g / g.sum() * 100).round(2)
    t = pd.DataFrame(imp).fillna(0).sort_values("without_market", ascending=False)
    t.reset_index(names="feature").to_csv(H.results_dir() / "E3_importance.csv", index=False)
    print(t.head(12).to_string())


def _moves(chg: pd.Series, thr: float = 0.03) -> np.ndarray:
    return np.select([chg > thr, chg < -thr], [2, 0], default=1)  # 0 down, 1 flat, 2 up


def cmd_e4a(d: H.HuntData) -> None:
    feats = _base(d).dropna(subset=[TARGET])
    feats = feats.assign(
        y=_moves(np.expm1(feats[TARGET]) / feats["last_value"] - 1),
        trend=_moves(feats["pct_change_7"].fillna(0.0)),
    )
    rows = []
    for fold in make_folds(d.last_date, H.HORIZON, H.N_FOLDS):
        train, test = split_fold(feats, fold)
        if test.empty:
            continue
        td = pd.to_datetime(train["target_date"])
        val = (td > td.max() - pd.Timedelta(days=28)).to_numpy()
        x, y = train[FEATURE_COLUMNS], train["y"].to_numpy()
        kw = dict(
            objective="multiclass",
            class_weight="balanced",
            random_state=SEED,
            deterministic=True,
            force_col_wise=True,
            verbose=-1,
            n_jobs=4,
            **DEFAULT_PARAMS,
        )
        es = lgb.LGBMClassifier(n_estimators=2000, **kw).fit(
            x[~val],
            y[~val],
            eval_X=(x[val],),
            eval_y=(y[val],),
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        best = max(int(es.best_iteration_ or 50), 50)
        clf = lgb.LGBMClassifier(n_estimators=best, **kw).fit(x, y)
        rows.append(
            test[[*SERIES_KEY, "target_date", "y", "trend"]].assign(
                lgbm=clf.predict(test[FEATURE_COLUMNS]), flat=1, fold=fold.number
            )
        )
    p = pd.concat(rows, ignore_index=True)
    p.to_parquet(H.results_dir() / "E4a_predictions.parquet", index=False)
    out = []
    groups = [("all", p), *p.groupby(p["commodity"].astype(str))]
    for crop, g in groups:
        r: dict[str, float | str | int | bool] = {
            "crop": crop,
            "n": len(g),
            "share_up": float((g.y == 2).mean()),
            "share_down": float((g.y == 0).mean()),
        }
        for m in ("lgbm", "flat", "trend"):
            r[f"macro_f1_{m}"] = f1_score(
                g.y, g[m], average="macro", labels=[0, 1, 2], zero_division=0
            )
            r[f"prec_up_{m}"] = precision_score(
                g.y, g[m], labels=[2], average="macro", zero_division=0
            )
            r[f"rec_up_{m}"] = recall_score(g.y, g[m], labels=[2], average="macro", zero_division=0)
            r[f"prec_down_{m}"] = precision_score(
                g.y, g[m], labels=[0], average="macro", zero_division=0
            )
            r[f"rec_down_{m}"] = recall_score(
                g.y, g[m], labels=[0], average="macro", zero_division=0
            )
        loss = {m: (g[m] != g.y).astype(float) * 100 for m in ("lgbm", "flat", "trend")}
        for b in ("flat", "trend"):
            dm = dm_test(loss["lgbm"], loss[b], g["target_date"], H.HORIZON)
            r[f"dm_p_vs_{b}"], r[f"dm_stat_vs_{b}"] = dm.p_value, dm.stat
        r["wins"] = bool(
            r["macro_f1_lgbm"] > max(r["macro_f1_flat"], r["macro_f1_trend"])  # type: ignore[call-overload]
            and all(
                r[f"dm_p_vs_{b}"] < H.MAX_P_VALUE and r[f"dm_stat_vs_{b}"] < 0
                for b in ("flat", "trend")
            )  # type: ignore[operator]
        )
        out.append(r)
    sc = pd.DataFrame(out)
    allrow = sc[sc.crop == "all"].iloc[0]
    f1_win = allrow["macro_f1_lgbm"] > max(allrow["macro_f1_flat"], allrow["macro_f1_trend"])
    verdict = (
        "WIN"
        if allrow["wins"]
        else (
            "macro-F1 beats both baselines but DM (0/1 loss) not significant/worse"
            if f1_win
            else "no win"
        )
    )
    H.log_experiment(
        "E4a_move_classification",
        "h=7 move classes up(>+3%)/down(<-3%)/flat; LGBM multiclass (balanced) vs always-flat "
        "and 7-day-trend persistence; DM on 0/1 misclassification loss",
        {"threshold": 0.03},
        {"scores": sc},
        {
            "macro_f1_lgbm": allrow["macro_f1_lgbm"],
            "macro_f1_flat": allrow["macro_f1_flat"],
            "macro_f1_trend": allrow["macro_f1_trend"],
            "dm_p_vs_flat": allrow["dm_p_vs_flat"],
            "dm_p_vs_trend": allrow["dm_p_vs_trend"],
        },
        verdict,
    )
    print(sc.round(3).to_string(index=False))


def _weekly_frame(d: H.HuntData) -> pd.DataFrame:
    """Weekly (Mon-Sun) mean observed price per series, >= 2 observations per week."""
    p = d.prices.assign(date=pd.to_datetime(d.prices["date"]))
    p["week"] = p["date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    w = p.groupby([*SERIES_KEY, "week"]).agg(
        price=("modal_price", "mean"), n=("modal_price", "size")
    )
    w = w[w["n"] >= 2].reset_index()
    return w


def _weekly_features(
    w: pd.DataFrame, weather: pd.DataFrame, k: int, last_week: pd.Timestamp
) -> pd.DataFrame:
    fest = sorted(pd.Timestamp(x) for v in festival_dates().values() for x in v)
    wx = weather.assign(date=pd.to_datetime(weather["date"]))
    wx["week"] = wx["date"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    rain = wx.groupby(["district", "week"])["rainfall_mm"].sum().rename("rain_w").reset_index()
    parts = []
    for key, g in w.groupby(SERIES_KEY, sort=True):
        s = g.set_index("week")["price"].reindex(
            pd.date_range(g["week"].min(), last_week, freq="7D")
        )
        x = s.ffill(limit=1)
        last = s.ffill()
        f = pd.DataFrame(index=s.index)
        f["origin_week"] = s.index
        f["target_week"] = s.index + pd.Timedelta(weeks=k)
        f["last_value"] = last
        f["log_last"] = np.log(last)
        for lag in (1, 2, 3, 4, 8, 13, 26, 52):
            f[f"wlag_{lag}_rel"] = np.log(x.shift(lag - 1)) - f["log_last"]
        for win in (4, 13):
            f[f"wmean_{win}_rel"] = np.log(s.rolling(win, min_periods=2).mean()) - f["log_last"]
        f["target"] = np.log(s.reindex(f["target_week"]).to_numpy())
        f[["commodity", "market", "variety"]] = key
        parts.append(f.reset_index(drop=True))
    out = pd.concat(parts, ignore_index=True)
    tw = pd.to_datetime(out["target_week"])
    out["weekofyear"] = tw.dt.isocalendar().week.astype(int).to_numpy()
    out["month"] = tw.dt.month
    start = tw - pd.Timedelta(days=6)
    out["fest_in_window"] = [
        int(any(a - pd.Timedelta(days=14) <= f <= b + pd.Timedelta(days=14) for f in fest))
        for a, b in zip(start, tw, strict=True)
    ]
    out["district"] = out["market"].map(market_districts())
    out = out.merge(
        rain.rename(columns={"week": "origin_week"}), on=["district", "origin_week"], how="left"
    )
    for c in ("commodity", "market", "variety"):
        out[c] = out[c].astype("category")
    return out[out["last_value"].notna()].reset_index(drop=True)


def cmd_e4b(d: H.HuntData) -> None:
    w = _weekly_frame(d)
    last_week = pd.Timestamp(d.last_date).to_period("W-SUN").end_time.normalize()
    if last_week > pd.Timestamp(d.last_date):
        last_week -= pd.Timedelta(weeks=1)  # last COMPLETE week
    feat_cols = [
        "commodity",
        "market",
        "variety",
        "log_last",
        *[f"wlag_{x}_rel" for x in (1, 2, 3, 4, 8, 13, 26, 52)],
        "wmean_4_rel",
        "wmean_13_rel",
        "weekofyear",
        "month",
        "fest_in_window",
        "rain_w",
    ]
    rows = []
    for k in (1, 2, 3, 4):
        f = _weekly_features(w, d.weather, k, last_week)
        f = f[f["target_week"] <= last_week]
        known = f.dropna(subset=["target"])
        # 52 folds x 2 origin-weeks (= the 52 x 14-day yardstick); last targets end at last_week.
        for i in range(H.N_FOLDS):
            end = last_week - pd.Timedelta(weeks=k + 2 * (H.N_FOLDS - 1 - i))
            cut = end - pd.Timedelta(weeks=1)
            train = known[known["target_week"] <= cut]
            test = known[(known["origin_week"] >= cut) & (known["origin_week"] <= end)]
            if test.empty or len(train) < 500:
                continue
            y = (train["target"] - train["log_last"]).to_numpy()
            tv = (train["target_week"] > cut - pd.Timedelta(weeks=4)).to_numpy()
            kw = dict(
                objective="quantile",
                alpha=0.5,
                random_state=SEED,
                deterministic=True,
                force_col_wise=True,
                verbose=-1,
                n_jobs=4,
                **DEFAULT_PARAMS,
            )
            x = train[feat_cols]
            es = lgb.LGBMRegressor(n_estimators=2000, **kw).fit(
                x[~tv],
                y[~tv],
                eval_X=(x[tv],),
                eval_y=(y[tv],),
                callbacks=[lgb.early_stopping(100, verbose=False)],
            )
            best = max(int(es.best_iteration_ or 50), 50)
            m = lgb.LGBMRegressor(n_estimators=best, **kw).fit(x, y)
            pred = np.exp(test["log_last"] + m.predict(test[feat_cols]))
            base = (
                test[[*SERIES_KEY]]
                .astype(str)
                .assign(
                    target_date=test["target_week"].to_numpy(),
                    actual=np.exp(test["target"]).to_numpy(),
                    horizon=k,
                    fold=i + 1,
                )
            )
            rows.append(base.assign(model="lgbm", pred=pred.to_numpy()))
            rows.append(base.assign(model="naive", pred=test["last_value"].to_numpy()))
    p = pd.concat(rows, ignore_index=True)
    p.to_parquet(H.results_dir() / "E4b_predictions.parquet", index=False)
    scores = []
    for k, g in p.groupby("horizon"):
        sc = H.score(g, "lgbm", horizon=max(1, int(k)))  # weekly steps: HAC lags k-1
        scores.append(sc.assign(horizon_weeks=k))
    sc = pd.concat(scores, ignore_index=True)
    allk = sc[sc.crop == "all"]
    verdict = (
        "WIN at " + ", ".join(f"{int(x)}w" for x in allk[allk.wins].horizon_weeks)
        if allk.wins.any()
        else "no win"
    )
    H.log_experiment(
        "E4b_weekly_mean",
        "Weekly mean price (Mon-Sun, >=2 obs), horizons 1-4 weeks, LGBM (L1, log-change) vs "
        "naive weekly (last weekly mean); 52 folds x 2 origin-weeks",
        {"min_obs_per_week": 2},
        {"scores": sc},
        {f"mape_lgbm_{int(r.horizon_weeks)}w": r.mape_lgbm for r in allk.itertuples()}
        | {f"mape_naive_{int(r.horizon_weeks)}w": r.mape_naive for r in allk.itertuples()}
        | {f"dm_p_{int(r.horizon_weeks)}w": r.dm_p for r in allk.itertuples()},
        verdict,
    )
    print(sc.round(4).to_string(index=False))


def cmd_e5(d: H.HuntData) -> None:
    src = H.results_dir() / "E0_reference_predictions.parquet"
    p = pd.read_parquet(src)
    p = p[p["model"].isin(["lgbm", "naive"])]
    wide = p.pivot_table(
        index=[*SERIES_KEY, "target_date", "fold"], columns="model", values="pred", observed=True
    ).reset_index()
    act = p[p.model == "naive"].set_index([*SERIES_KEY, "target_date"])["actual"]
    wide = wide.join(act, on=[*SERIES_KEY, "target_date"])
    grid = np.linspace(0, 1, 11)
    burn_in, min_hist = 12, 6
    rows = []
    for _key, g in wide.groupby(SERIES_KEY, observed=True):
        for k in sorted(g["fold"].unique()):
            if k <= burn_in:
                continue
            hist = g[g["fold"] < k]
            if hist["fold"].nunique() >= min_hist:
                errs = [
                    np.mean(
                        np.abs(hist.naive + w * (hist.lgbm - hist.naive) - hist.actual)
                        / hist.actual
                    )
                    for w in grid
                ]
                wgt = float(grid[int(np.argmin(errs))])
            else:
                wgt = 0.0
            cur = g[g["fold"] == k]
            comb = cur.naive + wgt * (cur.lgbm - cur.naive)
            base = cur[[*SERIES_KEY, "target_date", "actual"]].assign(fold=k, weight=wgt)
            rows += [
                base.assign(model="combo", pred=comb.to_numpy()),
                base.assign(model="naive", pred=cur.naive.to_numpy()),
                base.assign(model="lgbm", pred=cur.lgbm.to_numpy()),
            ]
    q = pd.concat(rows, ignore_index=True)
    for c in SERIES_KEY:
        q[c] = q[c].astype(str)
    sc = H.score(q, "combo")
    weights = q[q.model == "combo"].groupby([*SERIES_KEY])["weight"].mean().round(2).reset_index()
    allrow = sc[sc.crop == "all"].iloc[0]
    verdict = "WIN" if allrow["wins"] else "no win"
    H.log_experiment(
        "E5_combination",
        "Per-series weight w in naive + w*(LGBM - naive), w fit on earlier folds only "
        f"(expanding, >= {min_hist} folds), evaluated on folds {burn_in + 1}-{H.N_FOLDS}",
        {"grid": "0..1 step 0.1", "burn_in_folds": burn_in},
        {"scores": sc, "weights": weights},
        {
            "mape_combo": allrow["mape_combo"],
            "mape_naive": allrow["mape_naive"],
            "rel_improvement_pct": allrow["rel_improvement_pct"],
            "dm_p": allrow["dm_p"],
        },
        verdict,
    )
    print(sc.round(4).to_string(index=False))
    print(weights.to_string(index=False))


def write_report() -> None:  # filled in once all experiments have run
    raise NotImplementedError


COMMANDS = {
    "E0": cmd_e0,
    "E1": cmd_e1,
    "E2": cmd_e2,
    "E3": cmd_e3,
    "E4a": cmd_e4a,
    "E4b": cmd_e4b,
    "E5": cmd_e5,
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("command", choices=["snapshot", *COMMANDS, "report"])
    args = p.parse_args(argv)
    setup_logging()
    if args.command == "snapshot":
        cmd_snapshot()
        return 0
    if args.command == "report":
        write_report()
        return 0
    COMMANDS[args.command](H.load(_asof()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
