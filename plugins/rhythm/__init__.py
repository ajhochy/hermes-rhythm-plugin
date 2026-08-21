"""Rhythm plugin-native tool registration."""

from __future__ import annotations


def register(ctx) -> None:
    from plugins.rhythm.tools import register_tools

    register_tools(ctx)
