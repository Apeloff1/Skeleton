"""Brand-asset gate (port of hyperforge-cockpit-sota ``scripts/brand-check.mjs``).

A canvas app is almost always a game or visually rich app; those must ship a
custom share card rather than the platform placeholder. Games must also declare
``"type": "x:game"`` in ``src/lib/og/site.json`` and ship a 50:11 X feed card at
``public/x-banner.jpg``. Checked on the filesystem (not the served head) so
preview and mid-scaffold workspaces are judged the same way.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

# Over this, link scrapers time out or skip the image and the card silently
# fails to unfurl.
MAX_CARD_BYTES = 600 * 1024
OG_SITE_REL_PATH = "src/lib/og/site.json"
OG_SKILL_REL_PATH = ".grok/skills/og/SKILL.md"
CARD_CANDIDATES = ("public/og.jpg", "public/og.png")
BANNER_REL_PATH = "public/x-banner.jpg"


@dataclass(frozen=True)
class BrandFinding:
    """One brand finding. ``level`` is ``"warning"`` (blocking) or ``"note"``."""

    level: str
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        prefix = "BRAND WARNING" if self.level == "warning" else "BRAND NOTE"
        return f"{prefix}: {self.message}"


def read_og_site(root: Path) -> dict[str, Any]:
    """Parse ``site.json``; anything missing or malformed is an empty site."""
    try:
        data = json.loads((root / OG_SITE_REL_PATH).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def site_has_custom_card(site: Mapping[str, Any]) -> bool:
    return str(site.get("card", "")).lower() == "custom"


def site_declares_og_type_game(site: Mapping[str, Any]) -> bool:
    return str(site.get("type", "") or "").lower() == "x:game"


def find_card(root: Path) -> Path | None:
    for rel in CARD_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    return None


def compute_brand_warnings(
    *, has_canvas: bool, workspace_root: str | Path = "/workspace"
) -> list[BrandFinding]:
    root = Path(workspace_root)
    skill = root / OG_SKILL_REL_PATH
    site_path = root / OG_SITE_REL_PATH
    site = read_og_site(root)
    card = find_card(root)
    out: list[BrandFinding] = []

    if card is not None:
        if card.stat().st_size > MAX_CARD_BYTES:
            out.append(
                BrandFinding(
                    "warning",
                    "card-too-heavy",
                    f"{card} is over 600 KB; link scrapers skip images this heavy so the card "
                    f"silently fails to unfurl. Re-encode as JPEG (ffmpeg -q:v 4) per {skill}.",
                )
            )
        if not site_has_custom_card(site):
            out.append(
                BrandFinding(
                    "warning",
                    "card-flag-missing",
                    f'{card} exists but {site_path} is missing "card": "custom"; set it so '
                    f"identity is explicit (per {skill}).",
                )
            )
    elif has_canvas:
        out.append(
            BrandFinding(
                "warning",
                "game-card-missing",
                f"this looks like a game/canvas app but {root}/public/og.jpg is missing. Games "
                "must ship a custom 1200x630 share card built from the app's own art; the "
                f"placeholder is not acceptable. Finish the brand-asset pass per {skill}.",
            )
        )
    else:
        out.append(
            BrandFinding(
                "note",
                "placeholder-card",
                "no custom public/og.jpg; the platform placeholder will be served. Only plain "
                f"utilities should keep it; otherwise finish the brand-asset pass per {skill}.",
            )
        )

    if has_canvas and not site_declares_og_type_game(site):
        out.append(
            BrandFinding(
                "warning",
                "og-type-missing",
                f'this looks like a game/canvas app but {site_path} is missing "type": "x:game"; '
                "X uses og:type=x:game to present the unfurl as a game card.",
            )
        )

    if has_canvas and card is not None:
        banner = root / BANNER_REL_PATH
        if not banner.is_file():
            out.append(
                BrandFinding(
                    "warning",
                    "banner-missing",
                    f"this looks like a game/canvas app but {banner} is missing; games need a "
                    "50:11 X feed card (1200x264 JPEG).",
                )
            )
        elif banner.stat().st_size > MAX_CARD_BYTES:
            out.append(
                BrandFinding(
                    "warning",
                    "banner-too-heavy",
                    f"{banner} is over 600 KB; scrapers skip it so the feed card fails to unfurl.",
                )
            )
    return out


def brand_ok(findings: list[BrandFinding]) -> bool:
    """True when nothing blocking was found (notes are allowed)."""
    return not any(f.level == "warning" for f in findings)
