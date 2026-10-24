from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from phd_finder.config_loader import load_sources
from phd_finder.discover.http_util import get_text
from phd_finder.models import Position
from phd_finder.score import extract_email, make_id

PHD_TITLE = re.compile(
    r"\b(doktorand\w*|phd|ph\.?\s*d\.?|doctoral|promovend\w*|promovendus|zur promotion)\b",
    re.I,
)
SKIP_TITLE = re.compile(
    r"\b(werkstudent|ausbildung|hiwi|hilfskraft|professur|professor|praktikum|internship|shk|defended|congratulations|alumni|admissions|how to apply)\b",
    re.I,
)
VACANCY = re.compile(
    r"\b(position|opening|student|studentship|scholarship|programme|program|doktorand\w*|candidate|mitarbeiter\w*|researcher|looking for|stelle|vacancy|promovend\w*|promovendus)\b",
    re.I,
)


def fetch_universities() -> list[Position]:
    cfg = load_sources().get("universities", {})
    if not cfg.get("enabled", True):
        return []
    found: list[Position] = []
    for site in cfg.get("sites", []):
        name = site.get("name") or "University"
        city = site.get("city") or ""
        country = site.get("country") or ""
        for url in site.get("urls") or []:
            try:
                html = get_text(url)
            except Exception as exc:  # noqa: BLE001
                print(f"[university:{name}] {url} failed: {exc}")
                continue
            batch = parse_university_listing(
                html,
                url,
                institution=name,
                city=city,
                country=country,
            )
            print(f"[university:{name}] {len(batch)} PhD-like listings from {url}")
            found.extend(batch)
    uniq: dict[str, Position] = {}
    for pos in found:
        uniq.setdefault(pos.url or pos.id, pos)
    return list(uniq.values())


def parse_university_listing(
    html: str,
    page_url: str,
    *,
    institution: str,
    city: str,
    country: str,
) -> list[Position]:
    soup = BeautifulSoup(html, "html.parser")
    positions: list[Position] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if href.startswith(("#", "mailto:", "javascript:")) or "career-advice" in href.lower():
            continue
        parent = anchor.find_parent(["article", "li", "tr", "div"])
        title = _anchor_title(anchor, parent, href)
        if len(title) < 18 or not _is_phd_vacancy(title):
            continue
        url = urljoin(page_url, href)
        if url in seen or url.rstrip("/") == page_url.rstrip("/"):
            continue
        seen.add(url)
        extra = ""
        if parent:
            extra = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))[:1500]
        description = extra or title
        positions.append(
            _make_position(
                title=title,
                url=url,
                institution=institution,
                city=_city_from_title(title, city),
                country=_country_from_text(extra, country),
                description=description,
            )
        )
    if positions:
        return positions
    heading = soup.find(["h1", "h2"])
    page_title = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)) if heading else ""
    if _is_phd_vacancy(page_title):
        body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:2000]
        positions.append(
            _make_position(
                title=page_title,
                url=page_url,
                institution=institution,
                city=city,
                country=country,
                description=body,
            )
        )
    return positions


def _is_phd_vacancy(title: str) -> bool:
    if not title or SKIP_TITLE.search(title):
        return False
    if re.search(r"post-?dok|post-?doc", title, re.I) and not re.search(r"\bphd\b|\bdoktorand", title, re.I):
        return False
    if re.search(r"career advice|from doctoral|doctoral admissions|doctoral education|phd programmes?\b|phd opportunities\b", title, re.I):
        return False
    if re.search(r"\bmsc\b|\bm\.?\s*sc\.?\b|ma[iî]trise", title, re.I) and not re.search(
        r"\bphd\b|\bph\.?\s*d\.?\b|\bdoktorand", title, re.I
    ):
        return False
    return bool(PHD_TITLE.search(title) and VACANCY.search(title))


def _anchor_title(anchor, parent, href: str) -> str:
    own = ""
    for raw in (
        anchor.get_text(" ", strip=True),
        anchor.get("aria-label") or "",
        anchor.get("title") or "",
    ):
        cleaned = re.sub(r"\s+", " ", raw or "").strip()
        if cleaned:
            own = cleaned
            break
    # Prefer the anchor's own label when it already looks like a vacancy title.
    if len(own) >= 18:
        return own
    # Parent/card fallback only when the link text is empty (AcademicTransfer, CSIRO).
    if len(own) >= 8:
        return own
    candidates: list[str] = []
    if parent:
        parent_txt = re.sub(r"\s+", " ", parent.get_text(" ", strip=True)).strip()
        if parent_txt:
            cut = re.split(r"(?<=[.!?])\s+| {2,}", parent_txt, maxsplit=1)[0].strip()
            candidates.append(cut[:160].strip())
            candidates.append(parent_txt[:120].strip())
    slug = _title_from_slug(href)
    if slug:
        candidates.append(slug)
    for title in candidates:
        if len(title) >= 18 and _is_phd_vacancy(title):
            return title
    return candidates[0] if candidates else own


def _title_from_slug(href: str) -> str:
    m = re.search(r"/jobs/\d+/([a-z0-9][a-z0-9-]{10,})", href, re.I)
    if not m:
        return ""
    return m.group(1).replace("-", " ").strip()


def _city_from_title(title: str, default_city: str) -> str:
    low = title.lower()
    if "fernuniversität" in low or "fernuni" in low:
        return "Hagen"
    return default_city


def _country_from_text(text: str, default_country: str) -> str:
    if default_country:
        return default_country
    low = (text or "").lower()
    for name in (
        "united kingdom",
        "netherlands",
        "switzerland",
        "luxembourg",
        "germany",
        "australia",
        "canada",
        "sweden",
        "finland",
        "norway",
        "denmark",
        "france",
        "belgium",
        "austria",
        "ireland",
        "spain",
        "italy",
        "portugal",
        "poland",
    ):
        if name in low:
            return name.title() if name != "united kingdom" else "United Kingdom"
    return default_country


def _make_position(
    *,
    title: str,
    url: str,
    institution: str,
    city: str,
    country: str,
    description: str,
) -> Position:
    return Position(
        id=make_id(url, title, institution),
        title=title,
        institution=institution,
        city=city,
        country=country,
        url=url,
        source="university",
        description=description,
        email=extract_email(description),
        notes=institution,
    )
