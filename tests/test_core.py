from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from phd_finder.discover.academics_de import parse_academics_html
from phd_finder.discover.daad import parse_daad_feed
from phd_finder.discover.euraxess import parse_euraxess_html
from phd_finder.docs.generator import build_package, choose_cv
from phd_finder.models import Position
from phd_finder.score import classify_region, deadline_open, score_position
from phd_finder.track.db import Database


def test_region_priority_order():
    _, stuttgart = classify_region("Stuttgart", "Germany", "")
    _, germany = classify_region("Berlin", "Germany", "")
    _, ch = classify_region("Zurich", "Switzerland", "")
    _, europe = classify_region("Lund", "Sweden", "")
    _, au = classify_region("Melbourne", "Australia", "")
    _, canada = classify_region("Toronto", "Canada", "")
    tier, usa = classify_region("Boston", "United States", "United States")
    assert stuttgart > germany > ch > europe > au > usa
    assert canada == au
    assert tier == "excluded"


def test_closed_deadline_is_closed():
    yesterday = (date.today() - timedelta(days=2)).strftime("%d %B %Y")
    pos = Position(
        id="x",
        title="PhD in machine learning for genomics",
        city="Stuttgart",
        country="Germany",
        description="PhD machine learning gene expression clustering",
        deadline=yesterday,
        url="https://example.edu/jobs/1",
    )
    scored = score_position(pos)
    assert scored.status == "closed"
    assert scored.score == 0


def test_open_match_scores_positive():
    future = (date.today() + timedelta(days=20)).strftime("%d %B %Y")
    pos = Position(
        id="y",
        title="PhD position in computational biology and machine learning",
        institution="University of Stuttgart",
        city="Stuttgart",
        country="Germany",
        description="Doctoral researcher. Deep learning on transcriptomics and large language models.",
        deadline=future,
        url="https://example.edu/jobs/2",
    )
    scored = score_position(pos)
    assert scored.status == "new"
    assert scored.score > 0
    assert scored.region_tier == "stuttgart"
    assert "computational_biology" in scored.match_reasons


def test_short_keywords_do_not_match_inside_words():
    from phd_finder.score import looks_like_phd, topic_fit

    score, reasons = topic_fit("PhD on energy storage materials and coverage analysis")
    joined = " ".join(reasons).lower()
    assert "rag" not in joined
    assert looks_like_phd("Postdoctoral Positions in Data Science Stuttgart") is False
    assert looks_like_phd("Postdoctoral Researcher in Glial Biology and Epigenomics") is False
    assert looks_like_phd("Student Research Assistant in Computer Vision", "First Stage Researcher (R1)") is False
    assert looks_like_phd("PhD position in machine learning") is True
    assert looks_like_phd("PDF position-Artificial Intelligence and Software Systems for Breast Imaging") is False
    assert looks_like_phd("MSc Project-User Interface Design for Breast Cancer Screening") is False
    assert looks_like_phd("PhD Scholarship in Multimodal Imaging for Epilepsy Surgery Assessment") is True
    assert looks_like_phd("(MSc/PhD)-FeFET-based in-memory computing for AI") is True


def test_until_filled_stays_open():
    assert deadline_open("until filled") is True


def test_university_listing_beats_the_same_board_posting():
    common = dict(
        title="PhD in machine learning for genomics",
        city="Zurich",
        country="Switzerland",
        description="Doctoral position. Machine learning and gene expression.",
        deadline="until filled",
    )
    board = score_position(
        Position(id="b", source="euraxess", url="https://euraxess.ec.europa.eu/jobs/9", **common)
    )
    uni = score_position(
        Position(id="u", source="university", url="https://jobs.ethz.ch/job/view/1", institution="ETH Zurich", **common)
    )
    assert "university_site" in uni.match_reasons
    assert uni.score > board.score


def test_university_parser_keeps_phd_links():
    from phd_finder.discover.universities import parse_university_listing

    html = """
    <ul>
      <li><a href="/stuttgart/doktorand-robotik-ki-1">Doktorand (m/w/d) im Bereich Robotik und KI Universität Stuttgart</a></li>
      <li><a href="/stuttgart/werkstudent-1">Werkstudent:in im Bereich Controlling Universität Stuttgart</a></li>
      <li><a href="/news/defended">successfully defended his PhD thesis</a></li>
      <li><a href="/job/view/abc">Doctoral Student in Machine Learning and Medical Data Science</a></li>
    </ul>
    """
    found = parse_university_listing(
        html,
        "https://www.stellenwerk.de/stuttgart",
        institution="University of Stuttgart",
        city="Stuttgart",
        country="Germany",
    )
    titles = [p.title for p in found]
    assert len(found) == 2
    assert all(p.source == "university" for p in found)
    assert any("Robotik" in t for t in titles)
    assert all("Werkstudent" not in t for t in titles)


def test_university_parser_reads_empty_anchor_from_card():
    from phd_finder.discover.universities import parse_university_listing

    html = """
    <div class="job">
      <a href="/en/jobs/364611/phd-candidate-in-machine-learning-for-genomics/"></a>
      PhD Candidate in Machine Learning for Genomics Leiden University
    </div>
    """
    found = parse_university_listing(
        html,
        "https://www.academictransfer.com/en/jobs/?q=phd",
        institution="AcademicTransfer",
        city="",
        country="Netherlands",
    )
    assert len(found) == 1
    assert "Machine Learning" in found[0].title
    assert found[0].url.endswith("/phd-candidate-in-machine-learning-for-genomics/")


def test_auto_eligible_email_and_portal():
    from phd_finder.pipeline import _auto_eligible

    profile = {
        "pipeline": {
            "auto_apply": True,
            "auto_apply_email": True,
            "auto_apply_min_score": 0.15,
        }
    }
    assert _auto_eligible(
        {"score": 0.4, "application_mode": "email", "email": "pi@uni.de"}, profile
    )
    assert _auto_eligible(
        {"score": 0.4, "application_mode": "portal", "email": ""}, profile
    )
    assert not _auto_eligible(
        {"score": 0.05, "application_mode": "email", "email": "pi@uni.de"}, profile
    )
    assert not _auto_eligible(
        {"score": 0.4, "application_mode": "email", "email": "pi@uni.de"},
        {"pipeline": {"auto_apply": False}},
    )


def test_linkedin_parser_keeps_phd_drops_industry():
    from phd_finder.discover.linkedin import parse_linkedin_html

    html = """
    <ul>
      <li class="base-card">
        <a class="base-card__full-link" href="https://de.linkedin.com/jobs/view/phd-position-ml-at-kit-4479108427?position=1">
          <h3 class="base-search-card__title">PhD Position - Efficient Long-Context Large Models</h3>
        </a>
        <h4 class="base-search-card__subtitle">Karlsruhe Institute of Technology</h4>
        <span class="job-search-card__location">Eggenstein-Leopoldshafen, Baden-Württemberg, Germany 2 weeks ago</span>
      </li>
      <li class="base-card">
        <a class="base-card__full-link" href="https://au.linkedin.com/jobs/view/quant-researcher-4481380001">
          <h3 class="base-search-card__title">Quantitative Researcher - PhD: 2026</h3>
        </a>
        <h4 class="base-search-card__subtitle">Some Fund</h4>
        <span class="job-search-card__location">Sydney, New South Wales, Australia</span>
      </li>
      <li class="base-card">
        <a class="base-card__full-link" href="https://au.linkedin.com/jobs/view/tiktok-grad-4481380002">
          <h3 class="base-search-card__title">Audio Algorithm Researcher Graduate (Immersive Intelligent) - 2027 Start (PhD)</h3>
        </a>
        <h4 class="base-search-card__subtitle">TikTok</h4>
        <span class="job-search-card__location">Sydney, New South Wales, Australia</span>
      </li>
    </ul>
    """
    found = parse_linkedin_html(html, query="PhD position|Germany")
    assert len(found) == 1
    assert found[0].source == "linkedin"
    assert "Large Models" in found[0].title
    assert found[0].country == "Germany"
    assert found[0].city == "Eggenstein-Leopoldshafen"
    assert found[0].url == "https://www.linkedin.com/jobs/view/4479108427"


def test_euraxess_parser_reads_job_link():
    html = """
    <article>
      <a href="/jobs/123456">PhD in machine learning for genomics</a>
      <div>University of Stuttgart</div>
      <div>Germany</div>
      Posted on: 22 October 2026
      Application Deadline: 30 Nov 2026 - 23:59 (Europe/Berlin)
    </article>
    """
    found = parse_euraxess_html(html, "https://euraxess.ec.europa.eu", "machine learning")
    assert len(found) == 1
    assert found[0].url.endswith("/jobs/123456")
    assert "Stuttgart" in found[0].title or "machine learning" in found[0].title
    assert "Nov" in found[0].deadline


def test_daad_feed_parser():
    raw = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>PhD in Bioinformatics at University of Stuttgart</title>
        <link>https://www2.daad.de/phd/example-1</link>
        <description>University of Stuttgart. Application deadline: 15 Dec 2026. Machine learning on gene expression.</description>
        <pubDate>Wed, 22 Oct 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    found = parse_daad_feed(raw)
    assert len(found) == 1
    assert found[0].country == "Germany"
    assert found[0].source == "daad_phdgermany"


def test_academics_parser():
    html = """
    <article>
      <a href="/jobs/doktorand-ml-99">Doktorand/in Machine Learning Bioinformatik</a>
      <p>70174 Stuttgart Bewerbungsfrist: 01.12.2026</p>
    </article>
    """
    found = parse_academics_html(html, "https://www.academics.de/jobs?q=Doktorand", "Doktorand")
    assert len(found) == 1
    assert found[0].deadline == "01.12.2026"
    assert found[0].city == "Stuttgart"


def test_database_roundtrip_and_export(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    pos = Position(
        id="abc",
        title="PhD machine learning",
        institution="KIT",
        city="Karlsruhe",
        country="Germany",
        url="https://example.edu/a",
        source="test",
        score=0.8,
        priority_rank=1,
        status="new",
        pi_or_contact="Prof. Ada",
        deadline="until filled",
    )
    assert db.upsert_positions([pos]) == 1
    db.update_status("abc", "email_sent", notes="gmail_id=1")
    # A later discover must not clobber a sent application.
    pos.status = "new"
    pos.score = 0.2
    db.upsert_positions([pos])
    row = db.get("abc")
    assert row["status"] == "email_sent"
    assert row["notes"] == "gmail_id=1"
    exported = db.export_excel(tmp_path / "daily.xlsx")
    assert exported.exists()
    assert exported.with_suffix(".csv").exists()


def test_package_writes_pdf_and_checklist(tmp_path, monkeypatch):
    import phd_finder.docs.generator as gen

    monkeypatch.setattr(gen, "PACKAGES_DIR", tmp_path)
    monkeypatch.setattr(gen, "tailor_letter", lambda position, fallback: fallback)
    position = {
        "id": "pkg1",
        "title": "PhD in computational biology",
        "institution": "University of Stuttgart",
        "city": "Stuttgart",
        "country": "Germany",
        "description": "PhD. Please send transcript, thesis summary, and recommendation letters.",
        "pi_or_contact": "Prof. Example",
        "email": "jobs@example.edu",
        "url": "https://example.edu/phd",
        "application_mode": "email",
        "match_reasons": "computational_biology:genomics",
        "deadline": "until filled",
    }
    folder = build_package(position)
    assert (folder / "cover_letter.pdf").stat().st_size > 500
    assert "Stuttgart" in (folder / "cover_letter.txt").read_text(encoding="utf-8")
    checklist = (folder / "checklist.md").read_text(encoding="utf-8")
    assert "transcript" in checklist.lower()
    cv = choose_cv(position)
    assert cv.suffix == ".pdf"
