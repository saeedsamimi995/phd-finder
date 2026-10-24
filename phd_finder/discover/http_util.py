from __future__ import annotations

from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from phd_finder.config_loader import load_sources


class RetryableHTTPError(requests.HTTPError):
    """Transient HTTP status that is worth retrying."""


def session() -> requests.Session:
    cfg = load_sources()
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": cfg.get(
                "user_agent",
                "phd-finder/1.0 (personal research; saeedsamimi995@gmail.com)",
            ),
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        }
    )
    return s


def _request(url: str, params: dict[str, Any] | None = None) -> requests.Response:
    cfg = load_sources()
    timeout = int(cfg.get("request_timeout_seconds", 45))
    try:
        resp = session().get(url, params=params, timeout=timeout)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise RetryableHTTPError(str(exc)) from exc
    if resp.status_code in (429, 500, 502, 503, 504):
        raise RetryableHTTPError(f"{resp.status_code} for {url}")
    return resp


@retry(
    retry=retry_if_exception_type(RetryableHTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def get_text(url: str, params: dict[str, Any] | None = None) -> str:
    resp = _request(url, params)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


@retry(
    retry=retry_if_exception_type(RetryableHTTPError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    resp = _request(url, params)
    resp.raise_for_status()
    return resp.json()
