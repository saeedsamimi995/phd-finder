from __future__ import annotations

import re
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from phd_finder.config_loader import load_sources
from phd_finder.discover.http_util import get_text
from phd_finder.models import Position
from phd_finder.score import extract_email, make_id

FEEDS = [
    "https://api.daad.de/api/feeds/rss/en/phd.xml",
    "https://www.phdgermany.de/de/feed.xml",
    "http://www.phdgermany.de/de/feed.xml",
    "https://www2.daad.de/deutschland/promotion/phd/en/13306-phdgermany-database/?rss=1",
]

SEARCH_PAGES = [
    "https://www2.daad.de/deutschland/promotion/phd/en/13306-phdgermany-database/",
    "https://www.daad.de/en/studying-in-germany/phd-studies-research/phd-germany/",
]


def fetch_daad() -> list[Position]:
    cfg = load_sources().get("daad", {})
    if not cfg.get("enabled", True):
        return []
    positions: list[Position] = []
    for url in FEEDS:
        try:
            raw = get_text(url)
        except Exception as exc:  # noqa: BLE001
            print(f"[daad] feed {url} failed: {exc}")
            continue
        parsed = parse_daad_feed(raw)
        if parsed:
            positions.extend(parsed)
            break
    if not positions:
        for url in SEARCH_PAGES:
            try:
                html = get_text(url)
            except Exception as exc:  # noqa: BLE001
                print(f"[daad] page {url} failed: {exc}")
                continue
            positions.extend(parse_daad_html(html, url))
            if positions:
                break
    uniq: dict[str, Position] = {}
    for p in positions:
        uniq.setdefault(p.url or p.id, p)
    return list(uniq.values())


def parse_daad_feed(raw: str) -> list[Position]:
    feed = feedparser.parse(raw)
    positions: list[Position] = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = BeautifulSoup(entry.get("summary") or entry.get("description") or "", "html.parser").get_text(" ", strip=True)
        city, institution = _split_daad_meta(summary, title)
        positions.append(
            Position(
                id=make_id(link, title, institution),
                title=title,
                institution=institution,
                city=city,
                country="Germany",
                region_tier="germany",
                url=link,
                source="daad_phdgermany",
                description=summary[:4000],
                deadline=_deadline(summary),
                posted_date=(entry.get("published") or "")[:40],
                email=extract_email(summary),
            )
        )
    return positions


def parse_daad_html(html: str, page_url: str) -> list[Position]:
    soup = BeautifulSoup(html, "html.parser")
    positions: list[Position] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(title) < 12:
            continue
        if not re.search(r"phd|doctoral|doktor|promotion", title, re.I):
            if "phd" not in href.lower() and "promotion" not in href.lower():
                continue
        if href.startswith("#") or "javascript:" in href:
            continue
        url = urljoin(page_url, href)
        if url.rstrip("/") == page_url.rstrip("/"):
            continue
        positions.append(
            Position(
                id=make_id(url, title),
                title=title,
                country="Germany",
                url=url,
                source="daad_phdgermany",
                description=title,
            )
        )
    return positions


def _split_daad_meta(summary: str, title: str) -> tuple[str, str]:
    institution = ""
    city = ""
    m = re.search(r"(University|Universit[aä]t|Institute|Institut|Max Planck|Helmholtz|Fraunhofer)[^,.]{0,80}", summary, re.I)
    if m:
        institution = m.group(0).strip()
    return city, institution


def _deadline(text: str) -> str:
    m = re.search(
        r"(application deadline|bewerbungsschluss|deadline)[:\s]+([0-9]{1,2}[./][0-9]{1,2}[./][0-9]{2,4}|[0-9]{1,2}\s+\w+\s+\d{4})",
        text,
        re.I,
    )
    return m.group(2) if m else ""
