"""Polite HTTP: shared client, per-host rate limiting, retries (3x exponential backoff)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from cropcast.config import settings

log = logging.getLogger(__name__)

_last_call: dict[str, float] = {}
_lock = threading.Lock()


def make_client(**headers: str) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_s, connect=15.0),
        headers={"User-Agent": settings.user_agent, "Accept": "application/json", **headers},
        follow_redirects=True,
    )


def _throttle(url: str, min_interval: float) -> None:
    """Sleep so consecutive requests to the same host are >= min_interval seconds apart."""
    host = urlsplit(url).netloc
    with _lock:
        wait = _last_call.get(host, 0.0) + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def get_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any] | None = None,
    min_interval: float | None = None,
) -> Any:
    _throttle(url, settings.request_delay_s if min_interval is None else min_interval)
    resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()
