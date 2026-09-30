import asyncio
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "plugins/rhythm"
THEME_RELATIVE = "dashboard/theme/rhythm.css"


def test_rhythm_dashboard_manifest_declares_packaged_theme():
    dashboard_manifest = json.loads(
        (PLUGIN_ROOT / "dashboard/manifest.json").read_text(encoding="utf-8")
    )
    theme = dashboard_manifest["theme"]

    assert theme == {
        "name": "rhythm",
        "label": "Rhythm",
        "description": "Rhythm workspace colors for the Hermes dashboard",
        "css": "theme/rhythm.css",
    }
    assert (PLUGIN_ROOT / THEME_RELATIVE).is_file()

    package_manifest = json.loads(
        (PLUGIN_ROOT / "packaging/package-manifest.json").read_text(encoding="utf-8")
    )
    assert THEME_RELATIVE in package_manifest["content"]["assets"]
    assert THEME_RELATIVE in package_manifest["content"]["package_data"]


def test_rhythm_theme_contains_required_light_and_dark_tokens():
    css = (PLUGIN_ROOT / THEME_RELATIVE).read_text(encoding="utf-8")

    for token in (
        "#007760",
        "#D8EEE5",
        "#C0D7D1",
        "#03201D",
        "#19403A",
        "#2E5951",
        "#AC1730",
        "#00631B",
        "--color-primary",
        "--component-sidebar-background",
        "--color-border",
        "--color-text-primary",
        "--color-text-secondary",
        "--color-text-tertiary",
        "--color-destructive",
        "--color-success",
        "--color-ring",
        "--theme-radius",
    ):
        assert token in css

    assert ':root[data-theme="rhythm"]' in css
    assert "@media (prefers-color-scheme: dark)" in css


def test_dashboard_theme_seam_discovers_rhythm_without_core_special_case(monkeypatch):
    from hermes_cli import web_server
    from starlette.testclient import TestClient

    monkeypatch.setattr(web_server, "load_config", lambda: {"dashboard": {}})
    response = asyncio.run(web_server.get_dashboard_themes())
    rhythm = next(theme for theme in response["themes"] if theme["name"] == "rhythm")

    assert rhythm["stylesheet"] == "/dashboard-plugins/rhythm/theme/rhythm.css"
    stylesheet = TestClient(web_server.app).get(rhythm["stylesheet"])
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert ':root[data-theme="rhythm"]' in stylesheet.text

    core_files = (
        REPO_ROOT / "hermes_cli/web_server.py",
        REPO_ROOT / "web/src/themes/context.tsx",
        REPO_ROOT / "web/src/themes/types.ts",
        REPO_ROOT / "web/src/lib/api.ts",
    )
    for path in core_files:
        assert "rhythm" not in path.read_text(encoding="utf-8").lower()


def test_dashboard_theme_declaration_rejects_external_and_traversal_css(tmp_path):
    from hermes_cli.web_server import _normalise_dashboard_plugin_theme

    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    (dashboard / "valid.css").write_text(":root {}", encoding="utf-8")

    assert _normalise_dashboard_plugin_theme(
        "valid.css", plugin_name="example", dashboard_dir=dashboard
    ) == {
        "name": "example",
        "label": "example",
        "description": "",
        "css": "valid.css",
    }
    assert _normalise_dashboard_plugin_theme(
        "https://example.test/theme.css",
        plugin_name="example",
        dashboard_dir=dashboard,
    ) is None
    assert _normalise_dashboard_plugin_theme(
        "../theme.css", plugin_name="example", dashboard_dir=dashboard
    ) is None


def test_theme_generator_matches_committed_output():
    """RED first: tokens.json is the single source of truth. Regenerating from
    it must reproduce every committed generated theme file
    byte-for-byte."""
    from plugins.rhythm.theme import generate

    tokens = generate.load_tokens()
    assert generate.render_css(tokens) == generate.CSS_PATH.read_text(encoding="utf-8")
    assert generate.render_desktop_theme_ts(tokens) == generate.DESKTOP_THEME_PATH.read_text(encoding="utf-8")
    assert generate.render_embedded_theme_json(tokens) == generate.EMBEDDED_THEME_PATH.read_text(encoding="utf-8")


def test_theme_generator_check_fails_on_one_hex_drift(tmp_path, monkeypatch):
    """A single-hex drift in either committed file must fail `--check`."""
    from plugins.rhythm.theme import generate

    drifted_css = tmp_path / "rhythm.css"
    unchanged_ts = tmp_path / "theme.ts"
    drifted_css.write_text(
        generate.CSS_PATH.read_text(encoding="utf-8").replace("#007760", "#000000", 1), encoding="utf-8"
    )
    unchanged_ts.write_text(generate.DESKTOP_THEME_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(generate, "CSS_PATH", drifted_css)
    monkeypatch.setattr(generate, "DESKTOP_THEME_PATH", unchanged_ts)

    assert generate.main(["--check"]) == 1

    generate.main(["--write"])
    assert drifted_css.read_text(encoding="utf-8") == generate.render_css(generate.load_tokens())
    assert generate.main(["--check"]) == 0


def test_feature_pack_build_contains_theme(tmp_path):
    from plugins.rhythm.packaging.build import build_feature_pack

    package = build_feature_pack(REPO_ROOT, tmp_path / "package")
    assert (package / THEME_RELATIVE).read_text(encoding="utf-8") == (
        PLUGIN_ROOT / THEME_RELATIVE
    ).read_text(encoding="utf-8")
