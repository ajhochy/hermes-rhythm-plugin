#!/usr/bin/env python3
"""Single source of truth for the Rhythm theme: tokens.json in, generated
dashboard CSS, desktop TypeScript, and embedded-theme JSON out. All generated
files are committed; this script only re-derives them.

Regenerate after editing tokens.json:
    python3 plugins/rhythm/theme/generate.py --write

Check for drift (no writes, non-zero exit if either file is stale):
    python3 plugins/rhythm/theme/generate.py --check
"""
import argparse
import json
import sys
from pathlib import Path

THEME_DIR = Path(__file__).resolve().parent
TOKENS_PATH = THEME_DIR / "tokens.json"
CSS_PATH = THEME_DIR.parent / "dashboard" / "theme" / "rhythm.css"
DESKTOP_THEME_PATH = THEME_DIR.parent / "desktop" / "src" / "theme.ts"
EMBEDDED_THEME_PATH = THEME_DIR.parent / "desktop" / "rhythm-theme.json"


def load_tokens() -> dict:
    return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))


def render_css(tokens: dict) -> str:
    light, dark = tokens["light"], tokens["dark"]
    return f''':root[data-theme="rhythm"] {{
  color-scheme: light;

  --rhythm-primary: {light['primary']};
  --rhythm-sidebar: {light['sidebar']};
  --rhythm-border: {light['border']};
  --rhythm-text-primary: {light['textPrimary']};
  --rhythm-text-secondary: {light['textSecondary']};
  --rhythm-text-muted: {light['textMuted']};
  --rhythm-error: {light['error']};
  --rhythm-success: {light['success']};

  --background: {light['background']};
  --background-base: {light['background']};
  --background-alpha: 1;
  --midground: var(--rhythm-text-primary);
  --midground-base: var(--rhythm-text-primary);
  --midground-alpha: 1;
  --foreground: var(--rhythm-primary);
  --foreground-base: var(--rhythm-primary);
  --foreground-alpha: 1;

  --color-foreground: var(--rhythm-text-primary);
  --color-card: {light['card']};
  --color-card-foreground: var(--rhythm-text-primary);
  --color-popover: {light['popover']};
  --color-popover-foreground: var(--rhythm-text-primary);
  /* Slightly darker text/control aliases preserve AA contrast on white while
     the palette retains the requested brand hues above. */
  --color-primary: {light['primaryAccessible']};
  --color-primary-foreground: {light['primaryForeground']};
  --color-secondary: var(--rhythm-sidebar);
  --color-secondary-foreground: var(--rhythm-text-primary);
  --color-muted: {light['muted']};
  --color-muted-foreground: var(--rhythm-text-secondary);
  --color-accent: {light['accent']};
  --color-accent-foreground: {light['accentForeground']};
  --color-destructive: {light['destructiveAccessible']};
  --color-destructive-foreground: {light['destructiveForeground']};
  --color-success: {light['successAccessible']};
  --color-warning: {light['warning']};
  --color-border: var(--rhythm-border);
  --color-input: {light['input']};
  --color-ring: var(--rhythm-primary);

  --color-text-primary: var(--rhythm-text-primary);
  --color-text-secondary: var(--rhythm-text-secondary);
  /* #9CA3AF remains the muted palette token; body-sized tertiary copy uses
     the AA-safe secondary value on light surfaces. */
  --color-text-tertiary: var(--rhythm-text-secondary);
  --component-sidebar-background: var(--rhythm-sidebar);
  --component-sidebar-border-image: none;

  --radius: {light['radius']};
  --theme-radius: {light['radius']};
  --theme-terminal-background: {light['terminalBackground']};
  --theme-terminal-foreground: {light['terminalForeground']};
}}

@media (prefers-color-scheme: dark) {{
  :root[data-theme="rhythm"] {{
    color-scheme: dark;

    --rhythm-sidebar: {dark['sidebar']};
    --rhythm-border: {dark['border']};
    --rhythm-text-primary: {dark['textPrimary']};
    --rhythm-text-secondary: {dark['textSecondary']};
    --rhythm-text-muted: {dark['textMuted']};

    --background: {dark['background']};
    --background-base: {dark['background']};
    --midground: var(--rhythm-text-primary);
    --midground-base: var(--rhythm-text-primary);
    --foreground: {dark['primary']};
    --foreground-base: {dark['primary']};

    --color-foreground: var(--rhythm-text-primary);
    --color-card: {dark['card']};
    --color-card-foreground: var(--rhythm-text-primary);
    --color-popover: {dark['popover']};
    --color-popover-foreground: var(--rhythm-text-primary);
    --color-primary: {dark['primary']};
    --color-primary-foreground: {dark['primaryForeground']};
    --color-secondary: {dark['secondary']};
    --color-secondary-foreground: var(--rhythm-text-primary);
    --color-muted: {dark['muted']};
    --color-muted-foreground: var(--rhythm-text-secondary);
    --color-accent: {dark['accent']};
    --color-accent-foreground: {dark['accentForeground']};
    --color-destructive: {dark['destructiveAccessible']};
    --color-destructive-foreground: {dark['destructiveForeground']};
    --color-success: {dark['successAccessible']};
    --color-warning: {dark['warning']};
    --color-border: var(--rhythm-border);
    --color-input: {dark['input']};
    --color-ring: {dark['primary']};

    --color-text-primary: var(--rhythm-text-primary);
    --color-text-secondary: var(--rhythm-text-secondary);
    --color-text-tertiary: var(--rhythm-text-muted);
    --component-sidebar-background: var(--rhythm-sidebar);
  }}
}}
'''


def render_desktop_theme_ts(tokens: dict) -> str:
    light, dark = tokens["light"], tokens["dark"]

    def colors_block(t: dict, *, primary: str, primary_fg: str, secondary: str, background: str,
                      card: str, foreground: str) -> str:
        return f"""{{
    background: '{background}',
    foreground: '{foreground}',
    card: '{card}',
    cardForeground: '{foreground}',
    muted: '{t['muted']}',
    mutedForeground: '{t['textSecondary']}',
    popover: '{t['popover']}',
    popoverForeground: '{foreground}',
    primary: '{primary}',
    primaryForeground: '{primary_fg}',
    secondary: '{secondary}',
    secondaryForeground: '{foreground}',
    accent: '{t['accent']}',
    accentForeground: '{t['accentForeground']}',
    border: '{t['border']}',
    input: '{t.get('input', t['border'])}',
    ring: '{t.get('primary', primary)}',
    midground: '{t.get('primary', primary)}',
    destructive: '{t['destructiveAccessible']}',
    destructiveForeground: '{t['destructiveForeground']}',
    sidebarBackground: '{t.get('sidebar', secondary)}',
    sidebarBorder: '{t['border']}',
  }}"""

    light_colors = colors_block(
        light, primary=light['primaryAccessible'], primary_fg=light['primaryForeground'],
        secondary=light['sidebar'], background=light['background'], card=light['card'],
        foreground=light['textPrimary'],
    )
    dark_colors = colors_block(
        dark, primary=dark['primary'], primary_fg=dark['primaryForeground'],
        secondary=dark['secondary'], background=dark['background'], card=dark['card'],
        foreground=dark['textPrimary'],
    )

    return f"""/**
 * Rhythm desktop theme contribution, registered via THEMES_AREA so Rhythm's
 * palette shows up anywhere a built-in Hermes theme does (Cmd-K, Appearance
 * settings, /skin) without any per-surface wiring.
 *
 * GENERATED by generate.py from ../../theme/tokens.json. Do not hand-edit —
 * edit tokens.json and run:
 *   python3 plugins/rhythm/theme/generate.py --write
 */

export interface RhythmDesktopThemeColors {{
  background: string
  foreground: string
  card: string
  cardForeground: string
  muted: string
  mutedForeground: string
  popover: string
  popoverForeground: string
  primary: string
  primaryForeground: string
  secondary: string
  secondaryForeground: string
  accent: string
  accentForeground: string
  border: string
  input: string
  ring: string
  midground: string
  destructive: string
  destructiveForeground: string
  sidebarBackground: string
  sidebarBorder: string
}}

export interface RhythmDesktopTheme {{
  name: string
  label: string
  description: string
  colors: RhythmDesktopThemeColors
  darkColors: RhythmDesktopThemeColors
}}

export const rhythmDesktopTheme: RhythmDesktopTheme = {{
  name: 'rhythm',
  label: 'Rhythm',
  description: 'Rhythm workspace colors',
  colors: {light_colors},
  darkColors: {dark_colors},
}}

export default rhythmDesktopTheme
"""


def desktop_theme(tokens: dict) -> dict:
    light, dark = tokens["light"], tokens["dark"]

    def colors(t: dict, *, primary: str, primary_fg: str, secondary: str,
               background: str, card: str, foreground: str) -> dict:
        return {
            "background": background,
            "foreground": foreground,
            "card": card,
            "cardForeground": foreground,
            "muted": t["muted"],
            "mutedForeground": t["textSecondary"],
            "popover": t["popover"],
            "popoverForeground": foreground,
            "primary": primary,
            "primaryForeground": primary_fg,
            "secondary": secondary,
            "secondaryForeground": foreground,
            "accent": t["accent"],
            "accentForeground": t["accentForeground"],
            "border": t["border"],
            "input": t.get("input", t["border"]),
            "ring": t.get("primary", primary),
            "midground": t.get("primary", primary),
            "destructive": t["destructiveAccessible"],
            "destructiveForeground": t["destructiveForeground"],
            "sidebarBackground": t.get("sidebar", secondary),
            "sidebarBorder": t["border"],
        }

    return {
        "name": "rhythm",
        "label": "Rhythm",
        "description": "Rhythm workspace colors",
        "colors": colors(light, primary=light["primaryAccessible"],
                         primary_fg=light["primaryForeground"], secondary=light["sidebar"],
                         background=light["background"], card=light["card"],
                         foreground=light["textPrimary"]),
        "darkColors": colors(dark, primary=dark["primary"],
                             primary_fg=dark["primaryForeground"], secondary=dark["secondary"],
                             background=dark["background"], card=dark["card"],
                             foreground=dark["textPrimary"]),
    }


def render_embedded_theme_json(tokens: dict) -> str:
    return json.dumps(desktop_theme(tokens), indent=2) + "\n"


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write the generated files to disk")
    parser.add_argument("--check", action="store_true", help="exit 1 if generated output differs from disk")
    args = parser.parse_args(argv)

    tokens = load_tokens()
    css = render_css(tokens)
    theme_ts = render_desktop_theme_ts(tokens)
    embedded_theme_json = render_embedded_theme_json(tokens)

    if args.write:
        CSS_PATH.write_text(css, encoding="utf-8")
        DESKTOP_THEME_PATH.write_text(theme_ts, encoding="utf-8")
        EMBEDDED_THEME_PATH.write_text(embedded_theme_json, encoding="utf-8")
        return 0

    if args.check:
        stale = []
        if not CSS_PATH.is_file() or CSS_PATH.read_text(encoding="utf-8") != css:
            stale.append(str(CSS_PATH))
        if not DESKTOP_THEME_PATH.is_file() or DESKTOP_THEME_PATH.read_text(encoding="utf-8") != theme_ts:
            stale.append(str(DESKTOP_THEME_PATH))
        if not EMBEDDED_THEME_PATH.is_file() or EMBEDDED_THEME_PATH.read_text(encoding="utf-8") != embedded_theme_json:
            stale.append(str(EMBEDDED_THEME_PATH))
        if stale:
            print("Stale generated file(s), run with --write:\n  " + "\n  ".join(stale), file=sys.stderr)
            return 1
        return 0

    sys.stdout.write(css)
    sys.stdout.write(theme_ts)
    sys.stdout.write(embedded_theme_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
