from __future__ import annotations

import re

from bs4 import BeautifulSoup

from phd_finder.discover.http_util import get_text
from phd_finder.docs.generator import guess_contact
from phd_finder.score import extract_email


def enrich_position(row: dict) -> dict:
    url = (row.get("url") or "").strip()
    if not url.startswith("http"):
        return row
    try:
        html = get_text(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[enrich] {url} failed: {exc}")
        return row
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, nav, footer"):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    text = text[:12000]
    row["description"] = text or row.get("description") or ""
    if not row.get("email"):
        row["email"] = extract_email(text)
    guessed = guess_contact(text)
    if guessed:
        row["pi_or_contact"] = guessed
    if not row.get("deadline"):
        m = re.search(
            r"(?:Application Deadline|Bewerbungsfrist|Deadline)[:\s]+([0-9]{1,2}[./][0-9]{1,2}[./][0-9]{2,4}|[0-9]{1,2}\s+\w+\s+\d{4}[^.]{0,24})",
            text,
            re.I,
        )
        if m:
            row["deadline"] = m.group(1).strip()[:80]
    inst = soup.select_one("meta[property='og:site_name']")
    if inst and not row.get("institution"):
        row["institution"] = inst.get("content") or ""
    return row
