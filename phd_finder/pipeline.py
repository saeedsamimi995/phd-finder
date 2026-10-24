from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from phd_finder.config_loader import load_profile
from phd_finder.discover import discover_all
from phd_finder.discover.enrich import enrich_position
from phd_finder.docs.generator import build_package
from phd_finder.history import load_applied_entries
from phd_finder.models import Position
from phd_finder.paths import APPROVALS_FILE, REVIEW_QUEUE, ensure_dirs
from phd_finder.score import detect_application_mode, rank_positions, score_position
from phd_finder.track.db import Database


def run_discover(db: Database | None = None) -> int:
    db = db or Database()
    entries = load_applied_entries()
    imported = db.import_applied_history(entries)
    print(f"[discover] imported {imported} applied-history rows")
    found = discover_all()
    history_keys = db.known_history_keys()
    history_urls = db.known_applied_urls()
    scored: list[Position] = []
    for pos in found:
        scored.append(
            score_position(pos, history_keys=history_keys, history_urls=history_urls)
        )
    ranked = rank_positions(scored, top_n=10_000)
    rank_map = {p.id: p.priority_rank for p in ranked}
    for pos in scored:
        pos.priority_rank = rank_map.get(pos.id, 0)
    n = db.upsert_positions(scored)
    kept = sum(1 for p in scored if p.score > 0)
    print(f"[discover] stored {n} postings, {kept} with positive score")
    return kept


def run_prepare(db: Database | None = None, top_n: int | None = None) -> list[dict]:
    ensure_dirs()
    db = db or Database()
    profile = load_profile()
    top_n = top_n or int(profile.get("pipeline", {}).get("top_n_per_day", 15))
    rows = db.list_all()
    open_rows = [
        r
        for r in rows
        if (r.get("score") or 0) > 0 and r.get("status") in ("new", "docs_ready", "awaiting_approval")
    ]
    open_rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
    selected = open_rows[:top_n]
    queue_items = []
    for i, row in enumerate(selected, start=1):
        row = enrich_position(dict(row))
        if not row.get("application_mode") or row["application_mode"] == "portal":
            row["application_mode"] = detect_application_mode(row.get("description") or "", row.get("email") or "")
        row["priority_rank"] = i
        folder = build_package(row)
        auto = bool(profile.get("pipeline", {}).get("auto_apply", False))
        status = "awaiting_approval"
        decision = "pending"
        if auto:
            decision = "approve" if _auto_eligible(row, profile) else "pending"
        db.update_status(
            row["id"],
            status,
            package_path=str(folder),
            notes=row.get("notes") or "",
            priority_rank=i,
        )
        # Persist enriched fields
        pos = Position(
            id=row["id"],
            title=row.get("title") or "",
            institution=row.get("institution") or "",
            city=row.get("city") or "",
            country=row.get("country") or "",
            region_tier=row.get("region_tier") or "",
            pi_or_contact=row.get("pi_or_contact") or "",
            email=row.get("email") or "",
            url=row.get("url") or "",
            source=row.get("source") or "",
            description=row.get("description") or "",
            deadline=row.get("deadline") or "",
            posted_date=row.get("posted_date") or "",
            application_mode=row.get("application_mode") or "portal",
            match_reasons=row.get("match_reasons") or "",
            score=float(row.get("score") or 0),
            priority_rank=i,
            status=status,
            package_path=str(folder),
            notes=row.get("notes") or "",
            topic_score=float(row.get("topic_score") or 0),
            region_weight=float(row.get("region_weight") or 0),
        )
        db.upsert_positions([pos])
        queue_items.append(
            {
                "id": row["id"],
                "priority_rank": i,
                "score": row.get("score"),
                "title": row.get("title"),
                "institution": row.get("institution"),
                "pi_or_contact": row.get("pi_or_contact"),
                "city": row.get("city"),
                "country": row.get("country"),
                "region_tier": row.get("region_tier"),
                "url": row.get("url"),
                "deadline": row.get("deadline"),
                "application_mode": row.get("application_mode"),
                "email": row.get("email"),
                "package_path": str(folder),
                "status": status,
                "decision": decision,
            }
        )
    auto = bool(profile.get("pipeline", {}).get("auto_apply", False))
    instructions = (
        "auto_apply is on: email openings are approved and sent when Gmail is configured; "
        "portal openings become portal_ready (you still submit the form)."
        if auto
        else (
            "Set decision to 'approve' or 'skip' for each item, then run: "
            "python -m phd_finder approve --from-queue"
        )
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "instructions": instructions,
        "items": queue_items,
    }
    REVIEW_QUEUE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(queue_items, auto=auto)
    print(f"[prepare] {len(queue_items)} packages in {REVIEW_QUEUE}")
    return queue_items


def _auto_eligible(row: dict, profile: dict | None = None) -> bool:
    profile = profile or load_profile()
    pipe = profile.get("pipeline", {})
    if not pipe.get("auto_apply", False):
        return False
    min_score = float(pipe.get("auto_apply_min_score", 0.15))
    if float(row.get("score") or 0) < min_score:
        return False
    mode = row.get("application_mode") or "portal"
    has_email = bool(row.get("email"))
    if pipe.get("auto_apply_email", True) and mode in ("email", "hybrid") and has_email:
        return True
    # Portal listings are auto-queued as portal_ready (package only), not submitted.
    if mode == "portal" or not has_email:
        return True
    return False


def run_auto_apply(db: Database | None = None, *, dry_run: bool = False) -> dict[str, int]:
    """Approve the prepared queue and send email applications without a human review step."""
    db = db or Database()
    profile = load_profile()
    if not profile.get("pipeline", {}).get("auto_apply", False):
        print("[auto_apply] disabled in config/profile.yaml")
        return {"approved": 0, "skipped": 0, "portal_ready": 0, "email_sent": 0}
    if not REVIEW_QUEUE.exists():
        print("[auto_apply] no review_queue.json — run prepare first")
        return {"approved": 0, "skipped": 0, "portal_ready": 0, "email_sent": 0}
    payload = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
    decisions: dict[str, str] = {}
    for item in payload.get("items", []):
        decision = (item.get("decision") or "pending").lower()
        if decision == "skip":
            decisions[item["id"]] = "skip"
        elif decision == "approve" or _auto_eligible(item, profile):
            decisions[item["id"]] = "approve"
    counts = apply_decisions(db, decisions)
    sent = run_send(db, dry_run=dry_run)
    counts["email_sent"] = sent
    print(
        f"[auto_apply] email approved={counts['approved']} sent={sent} "
        f"portal_ready={counts['portal_ready']} skipped={counts['skipped']}"
    )
    return counts


def run_send(db: Database | None = None, *, dry_run: bool = False) -> int:
    """Send every approved email application. Returns how many were sent."""
    from phd_finder.apply.gmail import gmail_ready, send_application

    db = db or Database()
    rows = db.list_by_status(["approved"])
    if not rows:
        print("[send] no approved email applications")
        return 0
    dry = dry_run or os.getenv("PHD_FINDER_DRY_RUN") == "1"
    if not dry and not gmail_ready():
        print(
            "[send] Gmail not configured — save OAuth Desktop client JSON to "
            "config/gmail_credentials.json, then re-run send. "
            f"{len(rows)} approved email(s) waiting."
        )
        return 0
    sent = 0
    for row in rows:
        package = Path(row.get("package_path") or "")
        if not package.exists():
            db.update_status(row["id"], "failed", notes="package folder missing")
            print(f"[send] FAILED {row['id']}: package missing")
            continue
        if not row.get("email"):
            db.update_status(row["id"], "portal_ready", notes="approved but no email; use the portal")
            print(f"[send] PORTAL {row['id']}: no email")
            continue
        if dry:
            print(f"[send] DRY-RUN would email {row['email']} about {row['title']}")
            continue
        try:
            message_id = send_application(row, package)
        except Exception as exc:  # noqa: BLE001
            db.update_status(row["id"], "failed", notes=str(exc)[:500])
            print(f"[send] FAILED {row['id']}: {exc}")
            continue
        db.update_status(row["id"], "email_sent", notes=f"gmail_id={message_id}")
        print(f"[send] SENT {row['id']} -> {row['email']} ({message_id})")
        sent += 1
    return sent


def _write_markdown(items: list[dict], *, auto: bool = False) -> None:
    lines = [
        "# Review queue",
        "",
        (
            "auto_apply is on: email apps are sent when Gmail is ready; portal apps stay portal_ready."
            if auto
            else "Change `decision` in `review_queue.json` to `approve` or `skip`, then run `python -m phd_finder approve --from-queue`."
        ),
        "",
        "| rank | score | title | contact | region | mode | deadline | status | url |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        lines.append(
            "| {priority_rank} | {score} | {title} | {pi_or_contact} | {region_tier} | {application_mode} | {deadline} | awaiting_approval | {url} |".format(
                **{k: str(item.get(k) or "").replace("|", "/") for k in (
                    "priority_rank",
                    "score",
                    "title",
                    "pi_or_contact",
                    "region_tier",
                    "application_mode",
                    "deadline",
                    "url",
                )}
            )
        )
    (REVIEW_QUEUE.parent / "review_queue.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_decisions(db: Database, decisions: dict[str, str]) -> dict[str, int]:
    counts = {"approved": 0, "skipped": 0, "portal_ready": 0}
    for position_id, decision in decisions.items():
        row = db.get(position_id)
        if not row:
            print(f"[approve] unknown id {position_id}")
            continue
        decision = decision.lower().strip()
        if decision == "skip":
            db.update_status(position_id, "skipped", notes="skipped in review")
            counts["skipped"] += 1
        elif decision == "approve":
            mode = row.get("application_mode") or "portal"
            if mode == "portal" or not row.get("email"):
                db.update_status(position_id, "portal_ready", notes="approved; submit on the portal")
                counts["portal_ready"] += 1
            else:
                db.update_status(position_id, "approved")
                counts["approved"] += 1
        else:
            print(f"[approve] ignoring decision '{decision}' for {position_id}")
    APPROVALS_FILE.write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **counts}, indent=2),
        encoding="utf-8",
    )
    return counts
