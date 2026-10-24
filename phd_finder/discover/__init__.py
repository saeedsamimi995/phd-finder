from __future__ import annotations

import re

from phd_finder.discover.academics_de import fetch_academics_de
from phd_finder.discover.daad import fetch_daad
from phd_finder.discover.euraxess import fetch_euraxess
from phd_finder.discover.linkedin import fetch_linkedin
from phd_finder.discover.nature_careers import fetch_nature_careers
from phd_finder.discover.universities import fetch_universities
from phd_finder.models import Position


def discover_all() -> list[Position]:
    results: list[Position] = []
    for fetcher in (
        fetch_universities,
        fetch_linkedin,
        fetch_euraxess,
        fetch_daad,
        fetch_academics_de,
        fetch_nature_careers,
    ):
        try:
            results.extend(fetcher())
        except Exception as exc:  # noqa: BLE001 — isolate source failures
            print(f"[discover] {fetcher.__name__} failed: {exc}")
    return dedupe_positions(results)


def dedupe_positions(positions: list[Position]) -> list[Position]:
    """Keep one row per URL. If the same title is on a board and a university site, keep the university page."""
    by_url: dict[str, Position] = {}
    by_title: dict[str, str] = {}
    order: list[str] = []
    for pos in positions:
        url_key = (pos.url or "").strip().lower() or pos.id
        title_key = re.sub(r"[^a-z0-9]+", " ", (pos.title or "").lower()).strip()[:90]
        if url_key in by_url:
            continue
        if len(title_key) >= 36 and title_key in by_title:
            kept_url = by_title[title_key]
            kept = by_url[kept_url]
            if kept.source == "university" or pos.source != "university":
                continue
            by_url.pop(kept_url, None)
            order = [u for u in order if u != kept_url]
        by_url[url_key] = pos
        order.append(url_key)
        if len(title_key) >= 36:
            by_title[title_key] = url_key
    return [by_url[url] for url in order]
