"""One-off: recover modal-only rows from prices_rejected after migration 002.

Before 002, rows where a market reported only the modal price (min = max = 0) failed
`min <= modal <= max` and were quarantined. Now min/max are nullable, so those rows are
re-validated with the current contract and inserted into prices_raw.

Safety: rows are INSERTed with ON CONFLICT DO NOTHING — no existing prices_raw row is ever
updated. prices_rejected is left untouched (it is the audit log of what was quarantined).
Idempotent: a second run inserts 0 rows.

    uv run python scripts/recover_rejected.py            # against settings.database_url
    uv run python scripts/recover_rejected.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd
from sqlalchemy import text

from cropcast import db
from cropcast.ingest.mappings import apply_price_conventions
from cropcast.logging_setup import setup_logging
from cropcast.validate.schemas import validate

log = logging.getLogger("cropcast.recover")

COLUMNS = list(db.PRICE_COLUMNS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    setup_logging()
    engine = db.get_engine()
    db.init_db(engine)  # make sure migration 002 is applied first

    with engine.connect() as conn:
        rej = pd.read_sql(
            text(
                f"SELECT id, {', '.join(COLUMNS)}, reason FROM prices_rejected "
                "WHERE min_price = 0 AND max_price = 0 AND modal_price > 0 ORDER BY id"
            ),
            conn,
        )
    # The daily lookback re-quarantines the same row on several runs: one copy per key+values.
    distinct = rej.drop_duplicates(subset=COLUMNS, keep="first")
    candidates = apply_price_conventions(distinct)
    good, still_bad = validate(candidates)
    log.info(
        "re-validated modal-only rejects",
        extra={
            "rejected_rows": len(rej),
            "distinct": len(distinct),
            "pass_contract": len(good),
            "still_fail": len(still_bad),
            "still_fail_reasons": still_bad["reason"].value_counts().to_dict(),
        },
    )
    if args.dry_run:
        return 0
    inserted = db.insert_prices_if_absent(good, engine)
    log.info(
        "recovered modal-only rows",
        extra={"inserted": inserted, "key_already_present": len(good) - inserted},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
