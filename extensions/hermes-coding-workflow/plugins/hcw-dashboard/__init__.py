"""Dashboard-only native package: intentionally no mutation hooks."""
from __future__ import annotations
from typing import Any

def register(ctx: Any) -> None:
    return None
