"""Exercise the operator installer only in isolated temporary Hermes homes."""
from pathlib import Path
import tarfile

import pytest

from plugins.rhythm.packaging.build import build_feature_pack
from plugins.rhythm.packaging.install_local import BACKUP_SUFFIX, install_local
from plugins.rhythm.packaging.validate import PackagingGateError

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def package(tmp_path):
    return build_feature_pack(ROOT, tmp_path / "package")


def test_local_install_backs_up_once_copies_exact_bundles_and_keeps_backups_inert(package, tmp_path):
    from hermes_cli.plugins import PluginManager

    home = tmp_path / "home"
    agent = home / "plugins/rhythm"
    desktop = home / "desktop-plugins/rhythm"
    agent.mkdir(parents=True)
    desktop.mkdir(parents=True)
    (agent / "plugin.yaml").write_text("name: rhythm\nversion: 0.0.1\n")
    (desktop / "plugin.js").write_text("old desktop")
    (home / "auth.json").write_text("private auth sentinel")
    (home / "config.yaml").write_text("existing settings")
    unrelated = home / "plugins/untouched"
    unrelated.mkdir()
    (unrelated / "sentinel").write_text("keep")
    install_local(package, home)
    backups = []
    for target, file, content in ((agent, "plugin.yaml", "name: rhythm\nversion: 0.0.1\n"), (desktop, "plugin.js", "old desktop")):
        backup = target.with_name(target.name + BACKUP_SUFFIX) / "backup.tar"
        backups.append((backup, backup.read_bytes()))
        with tarfile.open(backup) as archive:
            assert archive.extractfile(f"rhythm/{file}").read().decode() == content
        assert not (backup.parent / file).exists()
    install_local(package, home)
    assert all(path.read_bytes() == original for path, original in backups)
    assert (desktop / "plugin.js").read_bytes() == (package / "desktop/dist/rhythm.mjs").read_bytes()
    assert {p.relative_to(agent): p.read_bytes() for p in agent.rglob("*") if p.is_file()} == {
        p.relative_to(package): p.read_bytes() for p in package.rglob("*") if p.is_file()
    }
    assert (home / "auth.json").read_text() == "private auth sentinel"
    assert (home / "config.yaml").read_text() == "existing settings"
    assert (unrelated / "sentinel").read_text() == "keep"
    assert [m.key for m in PluginManager()._scan_directory(home / "plugins", source="user")] == ["rhythm"]
    assert list((home / "desktop-plugins").glob("*/plugin.js")) == [desktop / "plugin.js"]


def test_local_install_refuses_tampering_and_symlink_before_touching_home(package, tmp_path):
    home = tmp_path / "home"
    bundle = package / "desktop/dist/rhythm.mjs"
    original = bundle.read_text()
    bundle.write_text(original + '\n//# sourceMappingURL=private.map\n')
    with pytest.raises(PackagingGateError):
        install_local(package, home)
    assert not home.exists()
    bundle.write_text(original)
    (home / "desktop-plugins").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "desktop-plugins/rhythm").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PackagingGateError):
        install_local(package, home)
    assert not (home / "plugins").exists()
    assert list(outside.iterdir()) == []


def test_local_install_restores_both_halves_if_second_replacement_fails(package, tmp_path, monkeypatch):
    home = tmp_path / "home"
    targets = [home / "plugins/rhythm", home / "desktop-plugins/rhythm"]
    for target in targets:
        target.mkdir(parents=True)
        (target / "sentinel").write_text("original")
    rename = Path.rename

    def fail_second(path, target):
        if path.name == "payload" and target == targets[1]:
            raise OSError("simulated copy failure")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_second)
    with pytest.raises(OSError, match="simulated copy failure"):
        install_local(package, home)
    for target in targets:
        assert list(target.iterdir()) == [target / "sentinel"]
        assert (target / "sentinel").read_text() == "original"
