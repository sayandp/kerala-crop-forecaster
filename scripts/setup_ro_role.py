"""Create / refresh the read-only role `cropcast_ro` used by the API and the dashboard.

SELECT on the serving tables and the bot's aggregate views only (bot_usage*, no chat ids).
Idempotent; keeps the password unless --rotate. Writes DATABASE_URL_RO to .env and (with
--github) to the GitHub secret, never to stdout.

    uv run python scripts/setup_ro_role.py --github     # against settings.database_url (Neon)
"""

from __future__ import annotations

import argparse
import sys

from cropcast import db
from cropcast.config import settings
from cropcast.roles import ensure_role, password_for, role_url, save_url

ROLE = "cropcast_ro"
ENV_KEY = "DATABASE_URL_RO"
TABLES = [
    "forecasts",
    "prices_clean",
    "model_metrics",
    "promotion_log",
    "shadow_predictions",
    "channel_stats",
    "pipeline_runs",
    "drift_reports",
    "bot_usage",  # views: aggregates only
    "bot_usage_daily",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rotate", action="store_true")
    p.add_argument("--github", action="store_true", help="also set the GitHub secret")
    args = p.parse_args(argv)
    engine = db.get_engine()
    db.init_db(engine)  # every granted table / view must exist first
    password = password_for(ENV_KEY, ROLE, args.rotate)
    verb = ensure_role(engine, ROLE, password, [f"GRANT SELECT ON {', '.join(TABLES)} TO {ROLE}"])
    save_url(ENV_KEY, role_url(settings.database_url, ROLE, password), args.github)
    print(
        f"{ROLE}: {verb}; SELECT on {len(TABLES)} tables/views; {ENV_KEY} written to .env"
        + (" and GitHub secrets" if args.github else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
