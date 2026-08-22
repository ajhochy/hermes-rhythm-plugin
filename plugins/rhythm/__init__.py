"""Rhythm plugin-native tool registration."""

from __future__ import annotations


def register(ctx) -> None:
    from .tools import register_tools

    register_tools(ctx)
