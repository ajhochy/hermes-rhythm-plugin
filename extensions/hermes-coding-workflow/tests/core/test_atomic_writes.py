from __future__ import annotations

import os
from pathlib import Path

import pytest

from hermes_coding_workflow import safety


def test_atomic_write_bytes_writes_regular_file_content(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    safety.atomic_write_bytes(target, b'{"a": 1}')
    assert target.read_bytes() == b'{"a": 1}'
    assert not target.is_symlink()


def test_atomic_write_text_writes_regular_file_content(tmp_path: Path) -> None:
    target = tmp_path / "log.txt"
    safety.atomic_write_text(target, "hello\n")
    assert target.read_text() == "hello\n"


def test_atomic_write_overwrites_existing_regular_file_atomically(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    target.write_text("old")
    safety.atomic_write_bytes(target, b"new")
    assert target.read_bytes() == b"new"


def test_atomic_write_leaves_no_temp_files_behind(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    safety.atomic_write_bytes(target, b"data")
    leftovers = [p for p in tmp_path.iterdir() if p.name != "record.json"]
    assert leftovers == []


def test_atomic_write_rejects_a_preexisting_symlink_leaf_without_following_it(tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("do not touch me")
    target = tmp_path / "leaf"
    target.symlink_to(victim)
    with pytest.raises(ValueError, match="path_scope_violation"):
        safety.atomic_write_bytes(target, b"attacker controlled")
    assert victim.read_text() == "do not touch me"
    assert target.is_symlink()


def test_atomic_write_rejects_a_symlinked_parent_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("do not touch me")
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="path_scope_violation"):
        safety.atomic_write_bytes(linked_parent / "victim.txt", b"attacker controlled")
    assert victim.read_text() == "do not touch me"


def test_atomic_write_parent_swap_cannot_redirect_replace_to_an_outside_victim(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "controlled"
    parent.mkdir()
    moved_parent = tmp_path / "controlled-original"
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "record.json"
    victim.write_text("do not touch me")
    target = parent / "record.json"
    real_replace = os.replace
    swapped = False

    def swap_parent_then_replace(src, dst, *args, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            if not kwargs.get("src_dir_fd"):
                real_replace(src, outside / Path(src).name)
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(safety.os, "replace", swap_parent_then_replace)
    with pytest.raises(ValueError, match="path_scope_violation"):
        safety.atomic_write_bytes(target, b"attacker controlled")
    assert victim.read_text() == "do not touch me"


def test_nofollow_log_open_rejects_parent_swap_without_touching_outside_leaf(tmp_path: Path, monkeypatch) -> None:
    parent = tmp_path / "workers"
    parent.mkdir()
    moved_parent = tmp_path / "workers-original"
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "runner.log"
    victim.write_text("do not touch me")
    real_open = os.open
    swapped = False

    def swap_parent_during_leaf_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if dir_fd is not None and path == "runner.log" and not swapped:
            swapped = True
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safety.os, "open", swap_parent_during_leaf_open)
    with pytest.raises(ValueError, match="path_scope_violation"):
        safety.open_nofollow_write_fd(parent / "runner.log")
    assert victim.read_text() == "do not touch me"
