from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from pathlib import Path

from phd_finder.config_loader import resolve_path


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _split_draft(draft: str, title: str, sender_name: str = "Applicant") -> tuple[str, str]:
    subject = f"PhD application — {title} — {sender_name}"
    lines = draft.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip() or subject
        if line.strip() == "" and i > 0:
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip() or draft
    return subject, body


def _credentials_path() -> Path:
    return resolve_path(os.getenv("GMAIL_CREDENTIALS_PATH", "config/gmail_credentials.json"))


def _token_path() -> Path:
    return resolve_path(os.getenv("GMAIL_TOKEN_PATH", "data/gmail_token.json"))


def gmail_ready() -> bool:
    return _credentials_path().exists()


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token = _token_path()
    client = _credentials_path()
    if not client.exists():
        raise FileNotFoundError(
            f"Gmail OAuth client JSON not found at {client}. "
            "Create a Desktop OAuth client in Google Cloud and save it there. See README."
        )
    if token.exists():
        creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES)
            creds = flow.run_local_server(port=0)
        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=creds)


def send_application(position: dict, package_dir: Path) -> str:
    from phd_finder.config_loader import load_profile

    profile = load_profile()["applicant"]
    sender = os.getenv("GMAIL_SENDER") or profile.get("email") or ""
    to_addr = (position.get("email") or "").strip()
    if not to_addr:
        raise ValueError("No recipient email on this position")
    draft_path = package_dir / "email_draft.txt"
    draft = draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""
    subject, body = _split_draft(
        draft,
        position.get("title") or "PhD position",
        sender_name=profile.get("full_name") or "Applicant",
    )

    msg = EmailMessage()
    msg["To"] = to_addr
    msg["From"] = sender
    msg["Subject"] = subject
    msg.set_content(body)

    attachments = [package_dir / "cover_letter.pdf", *sorted(package_dir.glob("CV_*.pdf"))]
    seen: set[str] = set()
    for path in attachments:
        if not path.exists() or path.name in seen:
            continue
        seen.add(path.name)
        msg.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=path.name,
        )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    service = get_service()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent.get("id", "")
