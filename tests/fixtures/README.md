# Test fixtures

| File | Real or synthetic | What it is |
|---|---|---|
| `sample_prices.parquet` | **Real** | Frozen extract of validated `prices_raw` (Agmarknet via the 2.0 report API), 2024-10-01 → 2026-09-30, 6 series: banana Nendran @ Koduvayoor and Kayamkulam, coconut Big @ Koduvayoor, rubber Other @ Mananthavady, pepper Other @ Kannur, tapioca Other @ Payyannur. Built by `scripts/make_sample_fixture.py --end 2026-09-30`. Frozen: do not regenerate (Phase 2 model-quality tests depend on it). |
| `agmarknet_v2_daily_sample.json` | **Real** (trimmed) | Agmarknet 2.0 daily state report for Kerala, 2026-10-01, trimmed to 8 commodities × ≤ 3 markets. Includes a Rs./Bundle commodity to test unit filtering. |
| `agmarknet_v2_month_sample.json` | **Real** (trimmed) | Agmarknet 2.0 date-wise report, Banana, Kerala, January 2018, trimmed to 3 markets × 3 dates. |
| `agmarknet_sample.json` | **HAND-BUILT** | data.gov.in daily-price response in the documented record shape. `api.data.gov.in` refused connections when Phase 1 was built, so no real capture was possible — replace with a real one (command in the file's `_fixture_note`). |
