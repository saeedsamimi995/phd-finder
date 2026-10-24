from __future__ import annotations

import json

import click

from phd_finder.paths import REVIEW_QUEUE, ensure_dirs
from phd_finder.pipeline import apply_decisions, run_auto_apply, run_discover, run_prepare, run_send
from phd_finder.track.db import Database


@click.group()
def main() -> None:
    """Discover, rank, package, and apply to PhD positions."""
    ensure_dirs()


@main.command("discover")
def discover_cmd() -> None:
    """Fetch open positions, score them, and store the table."""
    db = Database()
    run_discover(db)
    path = db.export_excel()
    click.echo(f"Exported {path}")


@main.command("prepare")
@click.option("--top-n", default=None, type=int, help="How many top positions to package today.")
def prepare_cmd(top_n: int | None) -> None:
    """Build cover letters, CV copies, and the review queue for the top positions."""
    run_prepare(Database(), top_n=top_n)


@main.command("approve")
@click.option("--from-queue", is_flag=True, help="Read decision fields from output/review_queue.json.")
@click.option("--ids", default="", help="Comma-separated position ids to approve.")
@click.option("--skip-ids", default="", help="Comma-separated position ids to skip.")
@click.option("--all", "approve_all", is_flag=True, help="Approve every item currently awaiting approval.")
def approve_cmd(from_queue: bool, ids: str, skip_ids: str, approve_all: bool) -> None:
    """Mark reviewed positions approved (email) or portal_ready."""
    db = Database()
    decisions: dict[str, str] = {}
    if from_queue:
        if not REVIEW_QUEUE.exists():
            raise click.ClickException("No review_queue.json. Run prepare first.")
        payload = json.loads(REVIEW_QUEUE.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            decision = (item.get("decision") or "pending").lower()
            if decision in ("approve", "skip"):
                decisions[item["id"]] = decision
        if not decisions:
            raise click.ClickException(
                "No approve/skip decisions in review_queue.json. Edit the decision field first."
            )
    if approve_all:
        for row in db.list_by_status(["awaiting_approval"]):
            decisions[row["id"]] = "approve"
    for position_id in [x.strip() for x in ids.split(",") if x.strip()]:
        decisions[position_id] = "approve"
    for position_id in [x.strip() for x in skip_ids.split(",") if x.strip()]:
        decisions[position_id] = "skip"
    if not decisions:
        waiting = db.list_by_status(["awaiting_approval"])
        if not waiting:
            click.echo("Nothing awaiting approval.")
            return
        click.echo("Awaiting approval:")
        for row in waiting:
            click.echo(
                f"  {row['priority_rank']:>2}  {row['id']}  {row['application_mode']:6}  {row['title'][:70]}"
            )
        click.echo("Set decision in output/review_queue.json, then: python -m phd_finder approve --from-queue")
        return
    counts = apply_decisions(db, decisions)
    click.echo(
        f"Approved for email: {counts['approved']}; portal-ready: {counts['portal_ready']}; skipped: {counts['skipped']}"
    )


@main.command("send")
@click.option("--dry-run", is_flag=True, help="Print what would be sent without calling Gmail.")
def send_cmd(dry_run: bool) -> None:
    """Send approved email applications via Gmail. Does nothing for portal positions."""
    from phd_finder.apply.gmail import gmail_ready

    if not dry_run and not gmail_ready():
        raise click.ClickException(
            "Gmail credentials missing. Save the Desktop OAuth JSON to config/gmail_credentials.json "
            "(see README) or pass --dry-run."
        )
    sent = run_send(Database(), dry_run=dry_run)
    click.echo(f"Sent {sent} email application(s).")


@main.command("mark-applied")
@click.argument("position_id")
def mark_applied_cmd(position_id: str) -> None:
    """Mark a portal application as submitted by you."""
    db = Database()
    row = db.get(position_id)
    if not row:
        raise click.ClickException(f"Unknown id {position_id}")
    db.update_status(position_id, "applied", notes="marked applied by user")
    click.echo(f"{position_id} -> applied")


@main.command("export")
def export_cmd() -> None:
    """Write today's ranked table to output/daily_YYYY-MM-DD.xlsx and .csv."""
    path = Database().export_excel()
    click.echo(f"Exported {path}")


@main.command("daily")
@click.option("--top-n", default=None, type=int)
@click.option("--dry-run", is_flag=True, help="Prepare and approve but do not call Gmail.")
def daily_cmd(top_n: int | None, dry_run: bool) -> None:
    """Discover, package, and auto-apply (email send when configured)."""
    from phd_finder.config_loader import load_profile

    db = Database()
    run_discover(db)
    run_prepare(db, top_n=top_n)
    # Apply before export so a locked spreadsheet cannot block sending.
    counts = None
    if load_profile().get("pipeline", {}).get("auto_apply", False):
        counts = run_auto_apply(db, dry_run=dry_run)
    path = db.export_excel()
    if counts is not None:
        click.echo(f"Daily auto-apply done. Table: {path}")
        click.echo(
            f"email_sent={counts.get('email_sent', 0)} portal_ready={counts.get('portal_ready', 0)} "
            f"approved_waiting_gmail={counts.get('approved', 0)}"
        )
    else:
        click.echo(f"Daily run ready for review. Table: {path}")
        click.echo("Edit output/review_queue.json decisions, then approve --from-queue and send.")


if __name__ == "__main__":
    main()
