from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from phd_finder.config_loader import load_sources
from phd_finder.discover.http_util import RetryableHTTPError, session
from phd_finder.models import Position
from phd_finder.score import extract_email, make_id

GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_ID = re.compile(r"/jobs/view/[^/]*?(\d{8,})")
LOC_NOISE = re.compile(
    r"\s*(?:\d+\s+(?:day|week|month|hour)s?\s+ago|Be an early applicant.*|Actively Hiring.*)$",
    re.I,
)
# Industry ads that want a PhD holder, not a PhD student seat.
INDUSTRY_PHD = re.compile(
    r"graduate\s*\(.*phd|-\s*phd:\s*\d{4}|phd required|holding a phd|"
    r"\b(senior|principal|staff|director|founding|lead)\b",
    re.I,
)
PHD_HINT = re.compile(
    r"\b(phd|ph\.?\s*d\.?|doktorand\w*|doctoral|promovend\w*|studentship|"
    r"doctor of philosophy)\b",
    re.I,
)


def fetch_linkedin() -> list[Position]:
    cfg = load_sources().get("linkedin", {})
    if not cfg.get("enabled", True):
        return []
    searches = cfg.get("searches") or _default_searches()
    delay = float(cfg.get("delay_seconds", 2.5))
    past = str(cfg.get("past_seconds", 2592000))
    starts = list(range(0, int(cfg.get("pages", 1)) * 10, 10))
    seen: dict[str, Position] = {}
    for i, search in enumerate(searches):
        keywords = (search.get("keywords") or "").strip()
        location = (search.get("location") or "").strip()
        if not keywords:
            continue
        for start in starts:
            if i or start:
                time.sleep(delay)
            try:
                html = _get_guest(keywords=keywords, location=location, start=start, past=past)
            except Exception as exc:  # noqa: BLE001
                print(f"[linkedin] {keywords!r} @ {location} failed: {exc}")
                break
            batch = parse_linkedin_html(html, query=f"{keywords}|{location}")
            if not batch:
                break
            for pos in batch:
                seen.setdefault(pos.url or pos.id, pos)
            print(f"[linkedin] {keywords!r} @ {location} start={start}: {len(batch)} PhD-like")
    return list(seen.values())


def parse_linkedin_html(html: str, query: str = "") -> list[Position]:
    soup = BeautifulSoup(html or "", "html.parser")
    positions: list[Position] = []
    for card in soup.select("li, div.base-card, div.job-search-card, div.base-search-card"):
        link = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not link:
            continue
        href = (link.get("href") or "").strip()
        url = _canonical_job_url(href)
        if not url:
            continue
        title_el = card.select_one("h3.base-search-card__title, h3, .base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle, h4, .base-search-card__subtitle")
        loc_el = card.select_one(".job-search-card__location, .base-search-card__metadata")
        title = _clean((title_el or link).get_text(" ", strip=True))
        company = _clean(company_el.get_text(" ", strip=True) if company_el else "")
        location = _clean_location(loc_el.get_text(" ", strip=True) if loc_el else "")
        if not _is_phd_listing(title):
            continue
        city, country = _split_location(location)
        text = _clean(card.get_text(" ", strip=True))[:2500]
        positions.append(
            Position(
                id=make_id(url, title, company),
                title=title,
                institution=company,
                city=city,
                country=country,
                url=url,
                source="linkedin",
                description=text,
                email=extract_email(text),
                notes=f"query={query}" if query else "",
                raw={"query": query, "location": location},
            )
        )
    uniq: dict[str, Position] = {}
    for pos in positions:
        uniq.setdefault(pos.url, pos)
    return list(uniq.values())


def _get_guest(*, keywords: str, location: str, start: int, past: str) -> str:
    params = {
        "keywords": keywords,
        "location": location,
        "start": str(start),
        "f_TPR": past,
    }
    for attempt in range(3):
        try:
            resp = session().get(GUEST_API, params=params, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise RetryableHTTPError(str(exc)) from exc
        if resp.status_code == 429:
            wait = 15 * (attempt + 1)
            print(f"[linkedin] rate-limited, sleeping {wait}s")
            time.sleep(wait)
            continue
        if resp.status_code in (500, 502, 503, 504):
            time.sleep(3 * (attempt + 1))
            continue
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text
    raise RetryableHTTPError(f"LinkedIn rate-limited for {keywords} @ {location}")


def _is_phd_listing(title: str) -> bool:
    if not title or not PHD_HINT.search(title):
        return False
    if INDUSTRY_PHD.search(title):
        return False
    if re.search(r"post-?dok|post-?doc", title, re.I):
        return False
    # Prefer student/position wording; allow bare "PhD in …" academic ads.
    if re.search(
        r"\b(position|student|studentship|candidate|researcher|opportunity|"
        r"programme|program|scholarship|doktorand|doctoral|promovend|"
        r"doctor of philosophy|phd:)\b",
        title,
        re.I,
    ):
        return True
    return bool(re.search(r"^phd\b|\bphd\b.*\b(in|on|for)\b", title, re.I))


def _canonical_job_url(href: str) -> str:
    if not href:
        return ""
    m = JOB_ID.search(href)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}"
    parsed = urlparse(href)
    if "/jobs/view/" not in parsed.path:
        return ""
    return f"https://www.linkedin.com{parsed.path}".rstrip("/")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_location(text: str) -> str:
    text = _clean(text)
    text = LOC_NOISE.sub("", text).strip(" ·|-")
    return text


def _split_location(location: str) -> tuple[str, str]:
    parts = [p.strip() for p in re.split(r",|\u00b7", location) if p.strip()]
    if not parts:
        return "", ""
    blob = " ".join(parts).lower()
    known = {
        "germany": "Germany",
        "switzerland": "Switzerland",
        "luxembourg": "Luxembourg",
        "netherlands": "Netherlands",
        "united kingdom": "United Kingdom",
        "uk": "United Kingdom",
        "australia": "Australia",
        "canada": "Canada",
        "france": "France",
        "sweden": "Sweden",
        "finland": "Finland",
        "norway": "Norway",
        "denmark": "Denmark",
        "belgium": "Belgium",
        "austria": "Austria",
        "ireland": "Ireland",
        "spain": "Spain",
        "italy": "Italy",
        "portugal": "Portugal",
        "poland": "Poland",
    }
    country = ""
    for key, name in known.items():
        if re.search(rf"\b{re.escape(key)}\b", blob):
            country = name
            break
    if not country:
        if "basel" in blob or "zurich" in blob or "geneva" in blob or "lausanne" in blob:
            country = "Switzerland"
        elif "baden-württemberg" in blob or "bavaria" in blob or "north rhine" in blob:
            country = "Germany"
    city = parts[0]
    if city.lower() in known or city.lower() in ("remote", "europe", "emea"):
        city = ""
    if re.search(r"metropolitan area|greater\b|area\b", city, re.I) and len(parts) == 1:
        # e.g. "Basel Metropolitan Area"
        city = parts[0].split()[0]
    return city, country


def _default_searches() -> list[dict[str, str]]:
    return [
        {"keywords": "PhD position", "location": "Germany"},
        {"keywords": "Doktorand", "location": "Germany"},
        {"keywords": "Doctoral researcher machine learning", "location": "Germany"},
        {"keywords": "PhD machine learning", "location": "Stuttgart"},
        {"keywords": "PhD student", "location": "Switzerland"},
        {"keywords": "PhD position", "location": "Luxembourg"},
        {"keywords": "PhD position", "location": "Netherlands"},
        {"keywords": "PhD studentship", "location": "United Kingdom"},
        {"keywords": "PhD machine learning", "location": "Europe"},
        {"keywords": "PhD bioinformatics", "location": "Europe"},
        {"keywords": "PhD position", "location": "Australia"},
        {"keywords": "PhD machine learning", "location": "Australia"},
        {"keywords": "PhD student", "location": "Canada"},
        {"keywords": "PhD machine learning", "location": "Canada"},
    ]
