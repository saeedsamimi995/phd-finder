from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup

from phd_finder.config_loader import load_sources
from phd_finder.discover.http_util import get_text
from phd_finder.models import Position
from phd_finder.score import extract_email, make_id

JOB_HREF = re.compile(r"/jobs/(\d+)")


# Facet term ids from the public EURAXESS search form (October 2026).
# Country term ids from the public EURAXESS search form.
COUNTRY_FACETS = {
    "Germany": "794",
    "Switzerland": "799",
    "Luxembourg": "796",
    "Australia": "802",
    "Canada": "682",
    "Austria": "791",
    "Belgium": "792",
    "Bulgaria": "746",
    "Croatia": "776",
    "Cyprus": "777",
    "Czech Republic": "747",
    "Denmark": "757",
    "Estonia": "758",
    "Finland": "760",
    "France": "793",
    "Greece": "779",
    "Hungary": "748",
    "Iceland": "762",
    "Ireland": "763",
    "Italy": "781",
    "Latvia": "766",
    "Lithuania": "767",
    "Malta": "782",
    "Netherlands": "798",
    "Norway": "768",
    "Poland": "749",
    "Portugal": "784",
    "Romania": "751",
    "Serbia": "786",
    "Slovakia": "753",
    "Slovenia": "787",
    "Spain": "788",
    "Sweden": "770",
    "Ukraine": "754",
    "United Kingdom": "771",
}
R1_FACET = "447"  # First Stage Researcher
FIELD_FACETS = {
    "computer science": "78",
    "biological sciences": "38",
    "medical sciences": "313",
}


def fetch_euraxess() -> list[Position]:
    cfg = load_sources()
    block = cfg.get("euraxess", {})
    if not block.get("enabled", True):
        return []
    base = block.get("base_url", "https://euraxess.ec.europa.eu").rstrip("/")
    pages = min(int(cfg.get("max_pages_per_source", 1)), 2)
    seen: dict[str, Position] = {}

    # (label, country hint, facet pairs, pages)
    searches: list[tuple[str, str, list[tuple[str, str]], int]] = [
        ("r1", "", [("job_research_profile", R1_FACET)], pages),
        ("germany-r1", "Germany", [("job_country", COUNTRY_FACETS["Germany"]), ("job_research_profile", R1_FACET)], pages),
        ("switzerland-r1", "Switzerland", [("job_country", COUNTRY_FACETS["Switzerland"]), ("job_research_profile", R1_FACET)], 1),
        ("luxembourg-r1", "Luxembourg", [("job_country", COUNTRY_FACETS["Luxembourg"]), ("job_research_profile", R1_FACET)], 1),
        ("australia-r1", "Australia", [("job_country", COUNTRY_FACETS["Australia"]), ("job_research_profile", R1_FACET)], 1),
        ("canada-r1", "Canada", [("job_country", COUNTRY_FACETS["Canada"]), ("job_research_profile", R1_FACET)], 1),
    ]
    already = {"Germany", "Switzerland", "Luxembourg", "Australia", "Canada"}
    for country, facet_id in COUNTRY_FACETS.items():
        if country in already:
            continue
        searches.append(
            (f"{country}-r1", country, [("job_country", facet_id), ("job_research_profile", R1_FACET)], 1)
        )
    for field_name, field_id in FIELD_FACETS.items():
        searches.append(
            (
                f"germany-{field_name}",
                "Germany",
                [
                    ("job_country", COUNTRY_FACETS["Germany"]),
                    ("job_research_profile", R1_FACET),
                    ("job_research_field", field_id),
                ],
                1,
            )
        )
    # Australia/Canada R1 pages are sparse; also search by research field (no R1),
    # which surfaces PhD scholarships that EURAXESS tags under computer/biological sciences.
    for country in ("Australia", "Canada"):
        for field_name, field_id in FIELD_FACETS.items():
            searches.append(
                (
                    f"{country.lower()}-{field_name}",
                    country,
                    [
                        ("job_country", COUNTRY_FACETS[country]),
                        ("job_research_field", field_id),
                    ],
                    1,
                )
            )

    for label, country, facets, page_count in searches:
        for page in range(page_count):
            params: list[tuple[str, str]] = [(f"f[{i}]", f"{name}:{value}") for i, (name, value) in enumerate(facets)]
            if page:
                params.append(("page", str(page)))
            url = f"{base}/jobs/search?{urlencode(params)}"
            try:
                html = get_text(url)
            except Exception as exc:  # noqa: BLE001
                print(f"[euraxess] {label} failed: {exc}")
                break
            found = parse_euraxess_html(html, base, label, country_hint=country)
            if not found:
                break
            for pos in found:
                seen.setdefault(pos.id, pos)
            time.sleep(0.4)
    return list(seen.values())


def parse_euraxess_html(html: str, base: str, query: str = "", country_hint: str = "") -> list[Position]:
    soup = BeautifulSoup(html, "html.parser")
    positions: list[Position] = []
    cards = soup.select("article, .node--type-job-offer, .views-row, li")
    if not cards:
        cards = [soup]

    for card in cards:
        link = None
        for a in card.select("a[href]"):
            href = a.get("href") or ""
            if JOB_HREF.search(href):
                link = a
                break
        if link is None:
            continue
        href = link.get("href") or ""
        url = urljoin(base, href)
        title = _clean(link.get_text(" ", strip=True))
        if len(title) < 8:
            heading = card.find(["h2", "h3", "h4"])
            title = _clean(heading.get_text(" ", strip=True) if heading else title)
        text = _clean(card.get_text(" ", strip=True))
        if not title or "cookie" in title.lower():
            continue
        country, city = _guess_place(text)
        if country_hint:
            country = country_hint
        deadline = _field(text, r"Application Deadline:\s*([0-9]{1,2}\s+\w+\s+\d{4})")
        posted = _field(text, r"Posted on:\s*([0-9]{1,2}\s+\w+\s+\d{4})")
        institution = _guess_institution(card, title)
        positions.append(
            Position(
                id=make_id(url, title, institution),
                title=title,
                institution=institution,
                city=city,
                country=country,
                url=url,
                source="euraxess",
                description=text[:4000],
                deadline=deadline,
                posted_date=posted,
                email=extract_email(text),
                notes=f"query={query}" if query else "",
                raw={"query": query},
            )
        )
    # Dedup within page
    uniq: dict[str, Position] = {}
    for p in positions:
        uniq.setdefault(p.url, p)
    return list(uniq.values())


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _field(text: str, pattern: str) -> str:
    m = re.search(pattern, text, flags=re.I)
    return _clean(m.group(1))[:180] if m else ""


def _guess_place(text: str) -> tuple[str, str]:
    countries = [
        "Germany",
        "Switzerland",
        "Luxembourg",
        "Australia",
        "Austria",
        "Netherlands",
        "Belgium",
        "France",
        "Sweden",
        "Denmark",
        "Norway",
        "Finland",
        "Italy",
        "Spain",
        "Portugal",
        "Ireland",
        "Poland",
        "Czech Republic",
        "United Kingdom",
        "Hungary",
    ]
    found = ""
    for c in countries:
        if re.search(rf"\b{re.escape(c)}\b", text):
            found = c
            break
    return found, ""


def _guess_institution(card, title: str) -> str:
    for sel in (".field--name-field-company", ".organisation", ".org"):
        node = card.select_one(sel)
        if node:
            return _clean(node.get_text(" ", strip=True))[:180]
    # Often the organisation sits in a heading before the job title link.
    lines = [_clean(x) for x in card.stripped_strings]
    for line in lines:
        if line and line != title and len(line) > 3 and "posted on" not in line.lower():
            if line.lower() in {"job", "funding", "hosting"}:
                continue
            return line[:180]
    return ""
