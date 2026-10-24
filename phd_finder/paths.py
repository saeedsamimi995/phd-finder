from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PACKAGES_DIR = OUTPUT_DIR / "packages"
TEMPLATES_DIR = Path(__file__).resolve().parent / "docs" / "templates"

PROFILE_YAML = CONFIG_DIR / "profile.yaml"
SOURCES_YAML = CONFIG_DIR / "sources.yaml"
DB_PATH = DATA_DIR / "phd_finder.db"
REVIEW_QUEUE = OUTPUT_DIR / "review_queue.json"
APPROVALS_FILE = OUTPUT_DIR / "approvals.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
