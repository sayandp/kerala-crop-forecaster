"""Trigger the daily pipeline exactly like the external cron does (workflow_dispatch API).

    GITHUB_DISPATCH_TOKEN=<fine-grained PAT> uv run python scripts/trigger_daily.py
    uv run python scripts/trigger_daily.py --show   # print the request cron-job.org must send

The token is read from settings (GITHUB_DISPATCH_TOKEN, e.g. in .env) and never printed.
GitHub answers 204 No Content on success. Because the run uses --once-per-day, triggering again
the same IST day writes and posts nothing.
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from cropcast.config import settings

WORKFLOW = "daily_pipeline.yml"
BODY = {"ref": "main", "inputs": {"mode": "scheduled"}}


def url() -> str:
    return f"https://api.github.com/repos/{settings.github_repo}/actions/workflows/{WORKFLOW}/dispatches"


def headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--show", action="store_true", help="print method, URL, headers and body")
    args = p.parse_args(argv)
    if args.show:
        print("POST", url())
        for k, v in headers("<YOUR_FINE_GRAINED_PAT>").items():
            print(f"{k}: {v}")
        print(json.dumps(BODY))
        return 0
    token = settings.github_dispatch_token
    if token is None:
        sys.exit("GITHUB_DISPATCH_TOKEN is not set")
    resp = httpx.post(url(), headers=headers(token.get_secret_value()), json=BODY, timeout=20)
    if resp.status_code == 204:
        print("dispatched: daily-pipeline (mode=scheduled) on main")
        return 0
    print(f"failed: HTTP {resp.status_code} {resp.text[:300]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
