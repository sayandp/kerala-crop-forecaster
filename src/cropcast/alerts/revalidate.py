"""On-demand ISR of the Vercel dashboard after the daily run (best effort, never fails a run)."""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cropcast.config import settings

log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, max=20),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
def _post(url: str, secret: str) -> httpx.Response:
    resp = httpx.post(url, headers={"x-revalidate-secret": secret}, timeout=20.0)
    resp.raise_for_status()
    return resp


def revalidate_dashboard(dry_run: bool = False) -> tuple[str, str | None]:
    """POST the revalidate route. Returns (status, reason); status is ok|skipped|warning."""
    url = settings.vercel_revalidate_url
    secret = settings.revalidate_secret
    if not url or secret is None:
        return "skipped", "VERCEL_REVALIDATE_URL / REVALIDATE_SECRET not set"
    if dry_run:
        return "skipped", "dry run"
    try:
        _post(url, secret.get_secret_value())
    except httpx.HTTPError as exc:
        # A stale dashboard self-heals within the hourly ISR window: warn, don't fail the run.
        log.warning("dashboard revalidation failed", extra={"error": type(exc).__name__})
        return "warning", type(exc).__name__
    return "ok", None
