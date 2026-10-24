"""Re-apply scoring to positions already stored. Used after matcher fixes."""

from phd_finder.models import Position
from phd_finder.score import rank_positions, score_position
from phd_finder.track.db import Database


def rescore(db: Database | None = None) -> int:
    db = db or Database()
    history_keys = db.known_history_keys()
    history_urls = db.known_applied_urls()
    scored = []
    for row in db.list_all(limit=None):
        pos = Position(
            id=row["id"],
            title=row.get("title") or "",
            institution=row.get("institution") or "",
            city=row.get("city") or "",
            country=row.get("country") or "",
            pi_or_contact=row.get("pi_or_contact") or "",
            email=row.get("email") or "",
            url=row.get("url") or "",
            source=row.get("source") or "",
            description=row.get("description") or "",
            deadline=row.get("deadline") or "",
            posted_date=row.get("posted_date") or "",
            application_mode=row.get("application_mode") or "portal",
            discovered_at=row.get("discovered_at") or "",
        )
        scored.append(score_position(pos, history_keys=history_keys, history_urls=history_urls))
    ranked = rank_positions(scored, top_n=10_000)
    ranks = {p.id: p.priority_rank for p in ranked}
    for pos in scored:
        pos.priority_rank = ranks.get(pos.id, 0)
    db.upsert_positions(scored)
    path = db.export_excel()
    kept = sum(1 for p in scored if p.score > 0)
    print(f"[rescore] {kept} open matches, table {path}")
    return kept


if __name__ == "__main__":
    rescore()
