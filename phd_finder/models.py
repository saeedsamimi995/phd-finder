from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any


STATUSES = (
    "new",
    "docs_ready",
    "awaiting_approval",
    "approved",
    "email_sent",
    "portal_ready",
    "applied",
    "skipped",
    "closed",
    "failed",
)


@dataclass
class Position:
    id: str
    title: str
    institution: str = ""
    city: str = ""
    country: str = ""
    region_tier: str = "unknown"
    pi_or_contact: str = ""
    email: str = ""
    url: str = ""
    source: str = ""
    description: str = ""
    deadline: str = ""
    posted_date: str = ""
    application_mode: str = "portal"  # email | portal | hybrid
    match_reasons: str = ""
    score: float = 0.0
    priority_rank: int = 0
    status: str = "new"
    package_path: str = ""
    notes: str = ""
    topic_score: float = 0.0
    region_weight: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        return d


def today_iso() -> str:
    return date.today().isoformat()
