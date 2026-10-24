from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from phd_finder.config_loader import load_profile
from phd_finder.docs.llm import tailor_letter
from phd_finder.paths import PACKAGES_DIR, TEMPLATES_DIR

BIO_HINTS = (
    "bio",
    "genom",
    "omic",
    "cancer",
    "medical",
    "clinical",
    "patholog",
    "health",
    "transcript",
)


def choose_cv(position: dict) -> Path:
    profile = load_profile()
    variants = profile["cv_variants"]
    blob = " ".join(
        str(position.get(k) or "")
        for k in ("title", "description", "match_reasons")
    ).lower()
    key = "bio" if any(h in blob for h in BIO_HINTS) else "ai"
    path = Path(variants.get(key) or variants["default"])
    if not path.exists():
        path = Path(variants["default"])
    return path


def fit_sentence(position: dict) -> str:
    reasons = str(position.get("match_reasons") or "")
    if "computational_biology" in reasons:
        return (
            "The project’s computational-biology and biomedical data focus lines up with "
            "my gene-expression clustering work and medical-imaging collaboration."
        )
    if "llm" in reasons:
        return (
            "The language-model and NLP angle lines up with my local LLM deployments "
            "and the Persian BERT classification study."
        )
    return (
        "The machine-learning methods in the posting line up with my thesis pipeline, "
        "graph and clustering experiments, and production ML work."
    )


def render_letter_text(position: dict) -> str:
    profile = load_profile()
    applicant = profile["applicant"]
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template_name = (
        "cover_letter.txt.j2"
        if (TEMPLATES_DIR / "cover_letter.txt.j2").exists()
        else "cover_letter.example.txt.j2"
    )
    template = env.get_template(template_name)
    recipient = _clean_person(position.get("pi_or_contact") or "")
    institution = _clean_institution(position.get("institution") or "")
    position = {**position, "institution": institution, "pi_or_contact": recipient}
    fallback = template.render(
        recipient=recipient,
        title=position.get("title") or "the advertised PhD position",
        institution=position.get("institution") or "",
        name=applicant["full_name"],
        thesis=applicant["thesis_title"],
        fit_sentence=fit_sentence(position),
        email=applicant["email"],
        phone=applicant["phone"],
    ).strip()
    tailored = tailor_letter(position, fallback)
    if "Sincerely" not in tailored and applicant["email"] not in tailored:
        tailored = tailored.rstrip() + f"\n\nSincerely,\n{applicant['full_name']}\n{applicant['email']}"
    place = " ".join(
        part
        for part in (
            position.get("institution") or "",
            position.get("city") or "",
            position.get("country") or "",
        )
        if part
    )
    header = (
        f"{applicant['full_name']}\n"
        f"{applicant['email']} | {applicant['phone']}\n"
        f"{date.today().strftime('%d %B %Y')}\n\n"
        f"{place}\n\n"
    )
    return header + tailored


def write_pdf(text: str, path: Path) -> None:
    try:
        _write_pdf_reportlab(text, path)
    except Exception:
        _write_pdf_stdlib(text, path)


def _write_pdf_reportlab(text: str, path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=11,
        leading=15,
        spaceAfter=8,
    )
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Cover letter — {load_profile()['applicant']['full_name']}",
    )
    story = []
    for block in text.split("\n\n"):
        safe = (
            block.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        story.append(Paragraph(safe, body))
        story.append(Spacer(1, 4))
    doc.build(story)


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf_stdlib(text: str, path: Path) -> None:
    """One-page text PDF used when ReportLab is not installed."""
    lines: list[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        while len(paragraph) > 90:
            cut = paragraph.rfind(" ", 0, 90)
            if cut < 40:
                cut = 90
            lines.append(paragraph[:cut])
            paragraph = paragraph[cut:].strip()
        lines.append(paragraph)
    lines = lines[:48]
    commands = ["BT", "/F1 11 Tf", "50 800 Td", "14 TL"]
    for i, line in enumerate(lines):
        if i:
            commands.append("T*")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>",
    ]
    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(sum(len(c) for c in chunks))
        chunks.append(f"{i} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
    xref_at = sum(len(c) for c in chunks)
    xref = [f"xref\n0 {len(objects)+1}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(b"".join(chunks + xref + [trailer]))


def requirement_checklist(position: dict) -> str:
    profile = load_profile()
    assets = profile.get("assets", {})
    blob = (position.get("description") or "").lower()
    lines = [
        "# Application checklist",
        "",
        f"- Position: {position.get('title')}",
        f"- URL: {position.get('url')}",
        f"- Mode: {position.get('application_mode')}",
        f"- Deadline: {position.get('deadline') or 'not stated (treated as open)'}",
        "",
        "## Attach these files",
        f"- CV: see {_cv_package_name(profile['applicant'])} in this folder",
        f"- Cover letter: cover_letter.pdf",
    ]
    mapping = [
        (("transcript", "grades", "noten"), "msc_transcript", "MSc transcript"),
        (("diploma", "degree certificate", "zeugnis"), "msc_diploma", "MSc diploma"),
        (("bachelor", "bsc", "b.sc"), "bsc_transcript", "BSc transcript"),
        (("recommendation", "reference", "referee"), "recommendation_bundle", "Recommendation letters"),
        (("thesis", "research statement", "summary"), "thesis_summary", "Thesis summary"),
        (("cv", "curriculum"), "personal_details", "Personal details (if a form asks)"),
    ]
    for keys, asset_key, label in mapping:
        if any(k in blob for k in keys) or asset_key in ("thesis_summary",):
            lines.append(f"- {label}: `{assets.get(asset_key, '')}`")
    if "manuscript" in blob or "publication" in blob:
        lines.append(f"- Manuscript: `{assets.get('manuscript', '')}`")
    lines += [
        "",
        "## Before you submit",
        "- Confirm the deadline is still open on the position page.",
        "- If the form asks for referee emails, use the letters already in About Apply and do not invent new referees.",
        "- Portal forms are not auto-filled (login/CAPTCHA/unique widgets). After you submit, run:",
        f"  python -m phd_finder mark-applied {position.get('id')}",
        "",
    ]
    return "\n".join(lines)


def email_draft(position: dict, letter: str) -> str:
    profile = load_profile()["applicant"]
    to = position.get("email") or ""
    subject = f"PhD application — {position.get('title')} — {profile['full_name']}"
    body = letter
    return (
        f"To: {to or '(no email on posting — use the portal checklist)'}\n"
        f"From: {profile['email']}\n"
        f"Subject: {subject}\n\n"
        f"{body}\n"
    )


def build_package(position: dict) -> Path:
    job_id = position["id"]
    folder = PACKAGES_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    letter = render_letter_text(position)
    write_pdf(letter, folder / "cover_letter.pdf")
    (folder / "cover_letter.txt").write_text(letter, encoding="utf-8")
    (folder / "email_draft.txt").write_text(email_draft(position, letter), encoding="utf-8")
    (folder / "checklist.md").write_text(requirement_checklist(position), encoding="utf-8")
    profile = load_profile()
    cv_name = _cv_package_name(profile["applicant"])
    cv = choose_cv(position)
    if cv.exists():
        shutil.copy2(cv, folder / cv_name)
    meta = {
        "id": job_id,
        "title": position.get("title"),
        "url": position.get("url"),
        "cv_source": str(cv),
        "cv_package_name": cv_name,
        "application_mode": position.get("application_mode"),
        "email": position.get("email"),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return folder


def _cv_package_name(applicant: dict) -> str:
    raw = (applicant.get("full_name") or "Applicant").strip()
    safe = re.sub(r"[^\w\-]+", "_", raw, flags=re.UNICODE).strip("_") or "Applicant"
    return f"CV_{safe}.pdf"


_TITLES = {"prof", "prof.", "dr", "dr.", "pd", "professor", "prof. dr", "prof dr"}
_GENERIC_INSTITUTIONS = {"university", "universität", "universitat", "germany", "deutschland", "switzerland", "luxembourg", "australia"}


def _clean_person(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" .,;:")
    if not text or text.lower() in _TITLES:
        return "Hiring Committee"
    return text


def _clean_institution(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" .,;:")
    if text.lower() in _GENERIC_INSTITUTIONS or len(text) < 4:
        return ""
    return text


def guess_contact(text: str) -> str:
    patterns = [
        r"((?:Prof\.?\s+|Professor\s+|Dr\.?\s+|PD\s+){1,3})([A-Z][a-zäöüé][\wÄÖÜäöüß\-]+(?:\s+[A-Z][a-zäöüé][\wÄÖÜäöüß\-]+){0,2})",
        r"(?:Contact person|Supervisor|Principal Investigator)\s*[:\-]\s*([A-Z][^\n,]{3,80})",
    ]
    for pat in patterns:
        m = re.search(pat, text or "")
        if not m:
            continue
        name = (m.group(m.lastindex) or "").strip(" .,;:")
        name = re.split(r"\b(Address|Email|E-mail|Phone|Tel|Fax|Department|Institute|University)\b", name)[0]
        name = name.strip(" .,;:")
        if name.lower() in _TITLES or len(name) < 3:
            continue
        prefix = m.group(1).strip() if m.lastindex and m.lastindex > 1 else ""
        full = f"{prefix} {name}".strip() if prefix and prefix.lower() not in _TITLES else name
        if full.lower() in _TITLES:
            continue
        return full[:120]
    return ""
