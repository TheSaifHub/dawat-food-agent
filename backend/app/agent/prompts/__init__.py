"""Dawat AI's system prompts (Phase 6d, D-035). One file per version; a version is never edited once used in a
run whose traces matter (evals, the demo). Change the prompt by adding system_v2.md and bumping CURRENT.

    system_prompt(version=CURRENT) → (text, version)   # the version goes into every agent_traces row
"""

from functools import cache
from pathlib import Path

CURRENT = "v6"
_DIR = Path(__file__).parent


@cache
def system_prompt(version: str = CURRENT) -> tuple[str, str]:
    path = _DIR / f"system_{version}.md"
    if not path.is_file():
        raise ValueError(f"no system prompt version {version!r}")
    return path.read_text(encoding="utf-8").strip(), version
