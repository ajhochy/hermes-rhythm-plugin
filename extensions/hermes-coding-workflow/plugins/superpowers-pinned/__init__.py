"""Native Hermes package registering the pinned upstream skills."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _skills_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here / "skills", here.parents[1] / "vendor" / "superpowers" / "skills"):
        if candidate.is_dir():
            return candidate
    raise RuntimeError("superpowers-pinned plugin: missing pinned skills; reinstall")


def register(ctx: Any) -> None:
    for skill in sorted(_skills_root().glob("*/SKILL.md")):
        ctx.register_skill(skill.parent.name, skill)
