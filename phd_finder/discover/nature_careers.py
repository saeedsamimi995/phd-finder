from __future__ import annotations

import re
import time
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from phd_finder.config_loader import load_profile, load_sources
from phd_finder.discover.http_util import get_text
from phd_finder.models import Position
from phd_finder.score import extract_email, make_id


def fetch_nature_careers() -> list[Position]:
    cfg = load_sources().get("nature_careers", {})
    if not cfg.get("enabled", True):
        return []
    keywords = cfg.get("keywords") or load_profile().get("search_queries", [])[:3]
    seen: dict[str, Position] = {}
    for keyword in keywords:
        url = f"https://www.nature.com/naturecareers/jobs/?text={quote(keyword)}"
        try:
            html = get_text(url)
        except Exception as exc:  # noqa: BLE001
            print(f"[nature] {url} failed: {exc}")
            continue
        for pos in parse_nature_html(html, url, keyword):
            seen.setdefault(pos.id, pos)
        time.sleep(0.4)
    return list(seen.values())


def parse_nature_html(html: str, page_url: str, keyword: str) -> list[Position]:
    soup = BeautifulSoup(html, "html.parser")
    positions: list[Position] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if not re.search(r"/naturecareers/job/|/jobs/\d+", href):
            continue
        if len(title) < 8:
            continue
        url = urljoin("https://www.nature.com", href)
        parent = a.find_parent(["article", "li", "div"])
        text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))[:2500] if parent else title
        country = ""
        for name in (
            "Germany",
            "Switzerland",
            "Luxembourg",
            "Australia",
            "Canada",
            "Netherlands",
            "France",
            "Sweden",
            "United Kingdom",
            "Finland",
            "Norway",
            "Denmark",
            "Belgium",
            "Austria",
        ):
            if name.lower() in text.lower():
                country = name
                break
        positions.append(
            Position(
                id=make_id(url, title),
                title=title,
                country=country,
                url=url,
                source="nature_careers",
                description=text,
                email=extract_email(text),
                notes=f"query={keyword}",
            )
        )
    uniq: dict[str, Position] = {}
    for p in positions:
        uniq.setdefault(p.url, p)
    return list(uniq.values())
