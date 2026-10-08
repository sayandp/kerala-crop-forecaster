"""Restricted Neon roles (scripts/setup_ro_role.py, scripts/setup_bot_role.py).

Idempotent: re-running keeps the password stored in .env unless rotated. The connection URL
goes to .env and optionally a GitHub secret -- never to stdout or logs.
"""

from __future__ import annotations

import re
import secrets
import subprocess
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from sqlalchemy import Engine, text

from cropcast.config import PROJECT_ROOT

ENV_PATH = PROJECT_ROOT / ".env"


def role_url(owner_url: str, role: str, password: str) -> str:
    u = urlsplit(owner_url.replace("postgresql+psycopg://", "postgresql://", 1))
    host = u.hostname or ""
    netloc = f"{role}:{quote(password, safe='')}@{host}" + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, netloc, u.path, u.query, ""))


def stored_password(env_key: str, role: str) -> str | None:
    env = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    m = re.search(rf"^{env_key}=postgresql://{role}:([^@]+)@", env, re.M)
    return unquote(m.group(1)) if m else None


def password_for(env_key: str, role: str, rotate: bool) -> str:
    current = None if rotate else stored_password(env_key, role)
    return current or secrets.token_urlsafe(24)


def ensure_role(engine: Engine, role: str, password: str, grants: list[str]) -> str:
    """CREATE/ALTER the login role, reset its table privileges, apply `grants`. Returns verb."""
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
        ).first()
        verb = "ALTER" if exists else "CREATE"
        conn.exec_driver_sql(f"{verb} ROLE {role} WITH LOGIN PASSWORD '{password}'")
        dbname = conn.execute(text("SELECT current_database()")).scalar_one()
        conn.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{dbname}" TO {role}')
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        conn.exec_driver_sql(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}")
        for grant in grants:
            conn.exec_driver_sql(grant)
    return "created" if verb == "CREATE" else "updated"


def save_url(env_key: str, url: str, github: bool) -> None:
    env = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    line = f"{env_key}={url}"
    if re.search(rf"^{env_key}=", env, re.M):
        env = re.sub(rf"^{env_key}=.*$", lambda _: line, env, flags=re.M)
    else:
        env = env.rstrip() + "\n" + line + "\n"
    ENV_PATH.write_text(env, encoding="utf-8")
    if github:
        subprocess.run(["gh", "secret", "set", env_key], input=url, text=True, check=True)
