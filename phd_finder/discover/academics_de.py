from __future__ import annotations

import re
import time
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from phd_finder.config_loader import load_sources
from phd_finder.discover.http_util import get_text
from phd_finder.models import Position
from phd_finder.score import extract_email, make_id

SEARCH_TEMPLATES = [
    "https://www.academics.de/stellenanzeigen?q={q}",
    "https://www.academics.com/jobs?q={q}",
]


def fetch_academics_de() -> list[Position]:
    cfg = load_sources().get("academics_de", {})
    if not cfg.get("enabled", True):
        return []
    keywords = cfg.get("keywords") or ["Doktorand", "PhD"]
    seen: dict[str, Position] = {}
    for keyword in keywords:
        html = ""
        page_url = ""
        for template in SEARCH_TEMPLATES:
            url = template.format(q=quote(keyword))
            try:
                html = get_text(url)
                page_url = url
                if "job" in html.lower() or "stelle" in html.lower():
                    break
            except Exception as exc:  # noqa: BLE001
                print(f"[academics] {url} failed: {exc}")
                html = ""
        if not html:
            continue
        for pos in parse_academics_html(html, page_url, keyword):
            seen.setdefault(pos.id, pos)
        time.sleep(0.4)
    return list(seen.values())


def parse_academics_html(html: str, page_url: str, keyword: str) -> list[Position]:
    soup = BeautifulSoup(html, "html.parser")
    positions: list[Position] = []
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if len(title) < 10:
            continue
        if not re.search(r"/job|/stelle|/jobs/|/position", href, re.I):
            continue
        if re.search(r"login|impressum|datenschutz|newsletter", href, re.I):
            continue
        url = urljoin(page_url, href)
        parent_text = ""
        parent = a.find_parent(["article", "li", "div"])
        if parent:
            parent_text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))[:2500]
        deadline = ""
        m = re.search(r"Bewerbungsfrist[:\s]+([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})", parent_text)
        if m:
            deadline = m.group(1)
        city = ""
        cm = re.search(r"\b(\d{5})\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)", parent_text)
        if cm:
            city = cm.group(2)
        positions.append(
            Position(
                id=make_id(url, title),
                title=title,
                city=city,
                country="Germany",
                url=url,
                source="academics_de",
                description=parent_text or title,
                deadline=deadline,
                email=extract_email(parent_text),
                notes=f"query={keyword}",
            )
        )
    uniq: dict[str, Position] = {}
    for p in positions:
        uniq.setdefault(p.url, p)
    return list(uniq.values())
