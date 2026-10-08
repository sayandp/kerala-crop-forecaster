"""Create / refresh the write role `cropcast_bot` used by the Telegram webhook on Render.

INSERT / UPDATE / DELETE (+ SELECT, needed for UPDATE ... WHERE, ON CONFLICT and RETURNING)
on the bot's own tables only: subscribers, user_alerts, telegram_updates, bot_events. Nothing
else -- prices and forecasts are read through cropcast_ro. Idempotent; keeps the password
unless --rotate. Writes DATABASE_URL_BOT to .env (and with --github to the GitHub secret),
never to stdout.

    uv run python scripts/setup_bot_role.py
"""

from __future__ import annotations

import argparse
import sys

from cropcast import db
from cropcast.config import settings
from cropcast.roles import ensure_role, password_for, role_url, save_url

ROLE = "cropcast_bot"
ENV_KEY = "DATABASE_URL_BOT"
TABLES = ["subscribers", "user_alerts", "telegram_updates", "bot_events"]
SEQUENCES = ["user_alerts_id_seq", "bot_events_id_seq"]


def grants() -> list[str]:
    return [
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TABLES)} TO {ROLE}",
        f"GRANT USAGE, SELECT ON SEQUENCE {', '.join(SEQUENCES)} TO {ROLE}",
    ]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rotate", action="store_true")
    p.add_argument("--github", action="store_true", help="also set the GitHub secret")
    args = p.parse_args(argv)
    engine = db.get_engine()
    db.init_db(engine)  # migration 008 creates the bot tables
    password = password_for(ENV_KEY, ROLE, args.rotate)
    verb = ensure_role(engine, ROLE, password, grants())
    save_url(ENV_KEY, role_url(settings.database_url, ROLE, password), args.github)
    print(
        f"{ROLE}: {verb}; write access to {', '.join(TABLES)}; {ENV_KEY} written to .env"
        + (" and GitHub secrets" if args.github else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
