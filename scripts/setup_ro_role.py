"""Create / refresh the read-only role `cropcast_ro` used by the API and the dashboard.

Grants SELECT on the serving tables only. Idempotent; re-running keeps the password unless
--rotate. Writes DATABASE_URL_RO to .env and (with --github) to the GitHub secret, never to
stdout.

    uv run python scripts/setup_ro_role.py --github     # against settings.database_url (Neon)
"""

from __future__ import annotations

import argparse
import re
import secrets
import subprocess
import sys
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy import text

from cropcast import db
from cropcast.config import PROJECT_ROOT, settings

ROLE = "cropcast_ro"
TABLES = [
    "forecasts",
    "prices_clean",
    "model_metrics",
    "promotion_log",
    "shadow_predictions",
    "channel_stats",
    "pipeline_runs",
    "drift_reports",
]


def ro_url(owner_url: str, password: str) -> str:
    u = urlsplit(owner_url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = u.hostname or ""
    netloc = f"{ROLE}:{quote(password, safe='')}@{host}" + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, netloc, u.path, u.query, ""))


def existing_password() -> str | None:
    env = (
        (PROJECT_ROOT / ".env").read_text(encoding="utf-8")
        if (PROJECT_ROOT / ".env").exists()
        else ""
    )
    m = re.search(r"^DATABASE_URL_RO=postgresql://cropcast_ro:([^@]+)@", env, re.M)
    return m.group(1) if m else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rotate", action="store_true")
    p.add_argument("--github", action="store_true", help="also set the GitHub secret")
    args = p.parse_args(argv)
    engine = db.get_engine()
    db.init_db(engine)  # drift_reports must exist before it is granted
    password = None if args.rotate else existing_password()
    from urllib.parse import unquote

    password = unquote(password) if password else secrets.token_urlsafe(24)
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
        ).first()
        verb = "ALTER" if exists else "CREATE"
        conn.exec_driver_sql(f"{verb} ROLE {ROLE} WITH LOGIN PASSWORD '{password}'")
        dbname = conn.execute(text("SELECT current_database()")).scalar_one()
        conn.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{dbname}" TO {ROLE}')
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
        conn.exec_driver_sql(f"GRANT SELECT ON {', '.join(TABLES)} TO {ROLE}")
    url = ro_url(settings.database_url, password)
    env_path = PROJECT_ROOT / ".env"
    env = env_path.read_text(encoding="utf-8")
    line = f"DATABASE_URL_RO={url}"
    env = (
        re.sub(r"^DATABASE_URL_RO=.*$", line, env, flags=re.M)
        if "DATABASE_URL_RO=" in env
        else env.rstrip() + "\n" + line + "\n"
    )
    env_path.write_text(env, encoding="utf-8")
    if args.github:
        subprocess.run(["gh", "secret", "set", "DATABASE_URL_RO"], input=url, text=True, check=True)
    print(
        f"{ROLE}: {verb.lower()}d; SELECT on {len(TABLES)} tables; DATABASE_URL_RO written to .env"
        + (" and GitHub secrets" if args.github else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
