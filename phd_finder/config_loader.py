from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from phd_finder.paths import PROFILE_YAML, ROOT, SOURCES_YAML, ensure_dirs


@lru_cache(maxsize=1)
def load_profile() -> dict[str, Any]:
    ensure_dirs()
    load_dotenv(ROOT / ".env")
    if not PROFILE_YAML.exists():
        example = PROFILE_YAML.with_name("profile.example.yaml")
        raise FileNotFoundError(
            f"Missing {PROFILE_YAML}. Copy {example} to config/profile.yaml "
            "and fill in your details (see README)."
        )
    with PROFILE_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_sources() -> dict[str, Any]:
    with SOURCES_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def reload_config() -> None:
    load_profile.cache_clear()
    load_sources.cache_clear()


def resolve_path(p: str | Path) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = ROOT / path
    return path
