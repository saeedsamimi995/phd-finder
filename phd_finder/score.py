from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

import dateparser

from phd_finder.config_loader import load_profile
from phd_finder.models import Position

EUROPE_COUNTRIES = {
    "germany",
    "deutschland",
    "switzerland",
    "schweiz",
    "luxembourg",
    "luxemburg",
    "austria",
    "österreich",
    "netherlands",
    "belgium",
    "france",
    "sweden",
    "denmark",
    "norway",
    "finland",
    "italy",
    "spain",
    "portugal",
    "ireland",
    "poland",
    "czech republic",
    "czechia",
    "hungary",
    "greece",
    "romania",
    "bulgaria",
    "croatia",
    "slovenia",
    "slovakia",
    "estonia",
    "latvia",
    "lithuania",
    "iceland",
    "united kingdom",
    "uk",
    "england",
    "scotland",
    "wales",
}


def make_id(url: str, title: str = "", institution: str = "") -> str:
    raw = (url or f"{title}|{institution}").strip().lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def classify_region(city: str, country: str, text: str = "") -> tuple[str, float]:
    profile = load_profile()
    weights = profile["region_weights"]
    hotspots = [c.lower() for c in profile.get("stuttgart_hotspot_cities", [])]
    exclude = [c.lower() for c in profile.get("exclude_countries", [])]

    blob = _norm(" ".join([city, country, text]))
    country_l = _norm(country)
    city_l = _norm(city)

    for ex in exclude:
        if ex and (ex == country_l or f" {ex} " in f" {blob} " or blob.endswith(ex) or blob.startswith(ex)):
            # Careful: 'us' alone is too short; rely on exclude list phrases
            if len(ex) <= 2 and ex not in ("us",):
                continue
            if ex in ("us", "usa") and ("united states" in blob or country_l in ("us", "usa", "united states")):
                return "excluded", 0.0
            if len(ex) > 2 and (ex in blob or ex == country_l):
                return "excluded", 0.0

    if any(h in city_l or h in blob for h in hotspots) or "baden-württemberg" in blob or "baden-wuerttemberg" in blob:
        return "stuttgart", float(weights["stuttgart"])

    if country_l in ("germany", "deutschland", "de") or " germany" in f" {blob}" or blob.endswith("germany"):
        return "germany", float(weights["germany"])

    if country_l in ("switzerland", "schweiz", "ch", "luxembourg", "luxemburg", "lu") or any(
        x in blob for x in ("switzerland", "schweiz", "luxembourg", "luxemburg")
    ):
        return "switzerland_luxembourg", float(weights["switzerland_luxembourg"])

    if country_l in ("australia", "au") or re.search(r"\baustralia\b", blob):
        return "australia", float(weights["australia"])

    if country_l in ("canada", "ca") or re.search(r"\bcanada\b", blob):
        return "canada", float(weights["canada"])

    if country_l in EUROPE_COUNTRIES or any(c in blob for c in EUROPE_COUNTRIES):
        return "europe", float(weights["europe"])

    # USA stays out. Canada is handled above.
    if any(x in blob for x in ("united states", " usa", "mexico", "boston", "california", "new york")):
        return "excluded", 0.0

    return "unknown", 0.15


def topic_fit(text: str) -> tuple[float, list[str]]:
    profile = load_profile()
    tracks = profile.get("keyword_tracks", {})
    blob = _norm(text)
    reasons: list[str] = []
    scores: list[float] = []

    for track_name, track in tracks.items():
        kws = track.get("keywords", [])
        weight = float(track.get("weight", 1.0))
        hits = [kw for kw in kws if _keyword_in(kw, blob)]
        if not hits:
            continue
        # Diminishing returns on number of hits
        hit_score = min(1.0, 0.18 * len(hits) + 0.12)
        scores.append(hit_score * weight)
        reasons.append(f"{track_name}:{','.join(hits[:4])}")

    if not scores:
        return 0.0, []
    # Combine tracks: max + 0.3 * mean of others
    scores_sorted = sorted(scores, reverse=True)
    combined = scores_sorted[0]
    if len(scores_sorted) > 1:
        combined += 0.3 * (sum(scores_sorted[1:]) / len(scores_sorted[1:]))
    return min(1.0, combined), reasons


def parse_deadline(deadline: str) -> date | None:
    if not deadline:
        return None
    low = deadline.lower().strip()
    if any(x in low for x in ("until filled", "open until", "rolling", "asap", "offen", "laufend")):
        return None  # treat as open
    dt = dateparser.parse(deadline, settings={"PREFER_DATES_FROM": "future"})
    if not dt:
        return None
    return dt.date()


def deadline_open(deadline: str, *, treat_until_filled_as_open: bool = True) -> bool:
    if not deadline:
        return True
    low = deadline.lower()
    if treat_until_filled_as_open and any(
        x in low for x in ("until filled", "rolling", "offen", "laufend", "no deadline")
    ):
        return True
    d = parse_deadline(deadline)
    if d is None:
        return True
    return d >= date.today()


def deadline_urgency(deadline: str) -> float:
    d = parse_deadline(deadline)
    if d is None:
        return 0.85  # rolling / unknown
    days = (d - date.today()).days
    if days < 0:
        return 0.0
    if days <= 7:
        return 1.0
    if days <= 21:
        return 0.9
    if days <= 45:
        return 0.75
    return 0.6


def freshness_boost(posted_date: str) -> float:
    if not posted_date:
        return 0.85
    dt = dateparser.parse(posted_date)
    if not dt:
        return 0.85
    days = (datetime.now(timezone.utc).date() - dt.date()).days
    if days <= 3:
        return 1.0
    if days <= 14:
        return 0.9
    if days <= 30:
        return 0.75
    return 0.55


def _keyword_in(keyword: str, blob: str) -> bool:
    kw = keyword.lower().strip()
    if not kw:
        return False
    if " " in kw or len(kw) > 4:
        return kw in blob
    return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", blob) is not None


def looks_like_phd(title: str, description: str = "") -> bool:
    title_l = _norm(title)
    blob = _norm(f"{title} {description}")
    if re.search(r"defended (his|her|their) phd|successfully defended", title_l):
        return False
    if re.search(r"post-?dok|post-?doc", title_l) and not re.search(r"\bph\.?d\b|\bdoktorand", title_l):
        return False
    # Canadian boards use "PDF" for Postdoctoral Fellow.
    if re.search(r"\bpdf position\b|^pdf\b", title_l) and not re.search(r"\bph\.?d\b", title_l):
        return False
    if re.search(r"\bmsc\b|\bm\.?\s*sc\.?\b|ma[iî]trise|projet de ma[iî]trise", title_l) and not re.search(
        r"\bph\.?d\b|\bdoktor", title_l
    ):
        return False
    title_blockers = (
        "student assistant",
        "student research assistant",
        "research assistant",
        "hiwi",
        "professor",
        "professorship",
    )
    if any(b in title_l for b in title_blockers) and not re.search(r"\bph\.?d\b|\bdoktor", title_l):
        return False
    positives = (
        "phd",
        "ph.d",
        "doctoral",
        "doctorate",
        "doktorand",
        "doktorandin",
        "promovieren",
        "promotion",
        "early stage researcher",
        "first stage researcher",
        "graduate researcher",
        "phd scholarship",
    )
    if "postdoctoral" in blob or "postdoc" in blob:
        positives = tuple(p for p in positives if p != "doctoral")
    negatives = ("professor", "professorship", "tenure", "bachelor", "internship only", "hiwi")
    if any(n in title_l for n in negatives) and not any(p in title_l for p in ("phd", "ph.d", "doktor")):
        return False
    return any(_keyword_in(p, blob) if " " not in p else p in blob for p in positives)


def detect_application_mode(text: str, email: str = "") -> str:
    blob = _norm(text)
    has_email = bool(email) or bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or ""))
    portal_hints = ("apply online", "application portal", "bewerbungsportal", "submit via", "online application")
    if has_email and any(h in blob for h in portal_hints):
        return "hybrid"
    if has_email and not any(h in blob for h in portal_hints):
        return "email"
    return "portal"


def extract_email(text: str) -> str:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text or "")
    return m.group(0) if m else ""


def already_applied(pos: Position, history_keys: set[str], history_urls: set[str]) -> bool:
    url = (pos.url or "").strip().lower()
    if url and url in history_urls:
        return True
    title_key = _norm(pos.title)
    if len(title_key) < 24:
        return False
    return any(title_key in key for key in history_keys)


def score_position(
    pos: Position,
    *,
    history_keys: set[str] | None = None,
    history_urls: set[str] | None = None,
) -> Position:
    profile = load_profile()
    history_keys = history_keys or set()
    history_urls = history_urls or set()

    blob = " ".join(
        [
            pos.title,
            pos.institution,
            pos.city,
            pos.country,
            pos.description,
            pos.pi_or_contact,
        ]
    )
    region_tier, region_weight = classify_region(pos.city, pos.country, blob)
    pos.region_tier = region_tier
    pos.region_weight = region_weight

    if region_tier == "excluded" or region_weight <= 0:
        pos.score = 0.0
        pos.status = "skipped"
        pos.match_reasons = "excluded_region"
        return pos

    if not looks_like_phd(pos.title, pos.description):
        pos.score = 0.0
        pos.status = "skipped"
        pos.match_reasons = "not_phd_like"
        return pos

    open_ok = deadline_open(
        pos.deadline,
        treat_until_filled_as_open=bool(profile.get("pipeline", {}).get("treat_until_filled_as_open", True)),
    )
    if profile.get("pipeline", {}).get("require_open_deadline", True) and not open_ok:
        pos.score = 0.0
        pos.status = "closed"
        pos.match_reasons = "deadline_passed"
        return pos

    t_score, reasons = topic_fit(blob)
    pos.topic_score = t_score
    min_topic = float(profile.get("pipeline", {}).get("min_topic_score", 0.12))
    if t_score < min_topic:
        pos.score = 0.0
        pos.status = "skipped"
        pos.match_reasons = "low_topic_fit"
        return pos

    urgency = deadline_urgency(pos.deadline)
    fresh = freshness_boost(pos.posted_date)
    origin = _source_weight(pos.source)
    if origin > 1:
        reasons.append("university_site")
    applied_penalty = 0.85 if already_applied(pos, history_keys, history_urls) else 0.0

    pos.score = round(region_weight * t_score * urgency * fresh * origin - applied_penalty, 4)
    if applied_penalty:
        reasons.append("already_seen_penalty")
        if pos.score <= 0:
            pos.status = "skipped"
            pos.match_reasons = ";".join(reasons)
            return pos

    pos.match_reasons = ";".join(reasons)
    if not pos.email:
        pos.email = extract_email(pos.description)
    if pos.application_mode == "portal":
        pos.application_mode = detect_application_mode(pos.description, pos.email)
    if pos.status in ("", "new") or pos.status == "skipped":
        pos.status = "new"
    return pos


def _source_weight(source: str) -> float:
    # Direct university and institute pages outrank aggregator boards.
    if (source or "").startswith("university"):
        return 1.35
    return 1.0


def rank_positions(positions: list[Position], top_n: int | None = None) -> list[Position]:
    profile = load_profile()
    top_n = top_n or int(profile.get("pipeline", {}).get("top_n_per_day", 15))
    scored = [p for p in positions if p.score > 0 and p.status not in ("closed", "skipped")]
    scored.sort(key=lambda p: p.score, reverse=True)
    for i, p in enumerate(scored, start=1):
        p.priority_rank = i
    return scored[:top_n]


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""
