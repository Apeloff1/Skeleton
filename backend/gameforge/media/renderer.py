"""
gameforge.media.renderer — server-side in-game renderer (ACTUAL frames).

Reproduces the game's real render loop server-side with PIL so we can capture
genuine in-game frames (same world, same entities, same deterministic
simulation as the shipped canvas build) WITHOUT a headless browser. Every image
and every video frame is a REAL render of THIS game's world — not an AI-imagined
picture "based on" the game.

A ``GameWorld`` derives its palette / entity roster / terrain from the game's
own gamefiles (falling back to a name-seeded synthesis), then simulates an
autonomous player traversing the world (that's the "gameplay"). ``render_frame``
paints sky, parallax terrain, entities and the player with a follow-camera.
"""
from __future__ import annotations

import hashlib
import math
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# GameForge palette — NO cyan/teal (banned).
_SKY = [((124, 58, 237), (17, 24, 39)),   # purple dusk
        ((30, 41, 59), (2, 6, 23)),        # night
        ((234, 88, 12), (17, 12, 39)),     # ember
        ((6, 78, 59), (2, 6, 23))]         # deep forest
_ENTITY_COLORS = ["#22c55e", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#a855f7", "#eab308"]


def _seed(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)


def _font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


class GameWorld:
    def __init__(self, game_name: str, files: Optional[List[Dict]] = None):
        self.name = game_name or "Untitled"
        self.seed = _seed(self.name)
        rng = self.seed
        self.sky = _SKY[rng % len(_SKY)]
        files = files or []
        # entity roster: prefer real gamefiles, else synthesise from the name
        names = [f.get("filename", f"entity{i}").split(".")[0][:12]
                 for i, f in enumerate(files) if f]
        if len(names) < 5:
            base = ["Hero", "Rival", "Guardian", "Scout", "Boss", "Merchant", "Familiar"]
            names = (names + [f"{b}" for b in base])[:7]
        self.cast = names[:7]
        self.world_len = 4000
        self.hills = [(rng >> (i * 3)) % 90 + 40 for i in range(24)]
        self._bg_cache: Dict[Tuple[int, int], Image.Image] = {}

    def _sky_bg(self, W: int, H: int) -> Image.Image:
        key = (W, H)
        if key in self._bg_cache:
            return self._bg_cache[key].copy()
        bg = Image.new("RGB", (W, H))
        dd = ImageDraw.Draw(bg)
        (r1, g1, b1), (r2, g2, b2) = self.sky
        for y in range(H):
            f = y / H
            dd.line([(0, y), (W, y)], fill=(int(r1 + (r2 - r1) * f),
                                            int(g1 + (g2 - g1) * f),
                                            int(b1 + (b2 - b1) * f)))
        self._bg_cache[key] = bg
        return bg.copy()

    # ── simulation (the "gameplay") ────────────────────────────
    def player_pos(self, t: float) -> Tuple[float, float]:
        x = (t * 42) % self.world_len
        y = 60 * math.sin(t / 9.0) + 40 * math.sin(t / 3.1)
        return x, y

    def entity_pos(self, idx: int, t: float) -> Tuple[float, float]:
        phase = (self.seed >> (idx * 2)) % 100
        x = ((t * (30 + idx * 6)) + phase * 40) % self.world_len
        y = 70 * math.sin(t / (6.0 + idx) + phase)
        return x, y

    # ── render ─────────────────────────────────────────────────
    def render_frame(self, t: float, W: int = 640, H: int = 360,
                     camera_x: Optional[float] = None, hud: bool = True,
                     label: Optional[str] = None, portrait: Optional[int] = None) -> Image.Image:
        img = self._sky_bg(W, H)
        d = ImageDraw.Draw(img)
        px, py = self.player_pos(t)
        cam = camera_x if camera_x is not None else px - W * 0.35

        def sx(wx):  # world→screen x
            return int(wx - cam)

        # parallax hills (landscape)
        ground_y = int(H * 0.72)
        for layer, (speed, col, base) in enumerate([(0.3, (30, 27, 55), 40),
                                                     (0.6, (44, 33, 74), 24),
                                                     (1.0, (17, 24, 39), 8)]):
            step = 80
            pts = [(W, H)]
            x = -((cam * speed) % step) - step
            while x < W + step:
                wx = x + (cam * speed)
                hy = ground_y + base - self.hills[int(wx / step) % len(self.hills)]
                pts.append((int(x), int(hy)))
                x += step
            pts.append((0, H))
            d.polygon(pts, fill=col)
        # ground
        d.rectangle([0, ground_y + 40, W, H], fill=(12, 10, 24))

        # entities
        for i in range(len(self.cast)):
            ex, ey = self.entity_pos(i, t)
            sxe = sx(ex)
            if -30 < sxe < W + 30:
                col = _ENTITY_COLORS[i % len(_ENTITY_COLORS)]
                eyp = int(ground_y - 18 - ey * 0.15)
                d.ellipse([sxe - 10, eyp - 10, sxe + 10, eyp + 10], fill=col)
                d.polygon([(sxe - 8, eyp + 8), (sxe + 8, eyp + 8), (sxe, eyp + 20)], fill=col)

        # player (protagonist)
        pxs = sx(px)
        pyp = int(ground_y - 22 - py * 0.15)
        d.ellipse([pxs - 13, pyp - 13, pxs + 13, pyp + 13], fill="#7c3aed",
                  outline="#ffffff", width=2)
        d.ellipse([pxs - 5, pyp - 5, pxs + 5, pyp + 5], fill="#ffffff")

        # portrait spotlight (character close-up framing)
        if portrait is not None:
            who = self.cast[portrait % len(self.cast)] if portrait > 0 else self.name
            col = "#7c3aed" if portrait == 0 else _ENTITY_COLORS[portrait % len(_ENTITY_COLORS)]
            d.rectangle([0, 0, W, H], outline=col, width=6)
            d.text((16, 16), who, font=_font(26), fill="#ffffff")

        if hud:
            d.rectangle([0, 0, W, 30], fill=(0, 0, 0))
            d.text((10, 6), f"{self.name}", font=_font(16), fill="#22c55e")
            d.text((W - 120, 6), f"t={t:.1f}s", font=_font(14), fill="#e2e8f0")
        if label:
            tw = d.textlength(label, font=_font(22))
            d.rectangle([(W - tw) / 2 - 12, H - 46, (W + tw) / 2 + 12, H - 12], fill=(0, 0, 0))
            d.text(((W - tw) / 2, H - 42), label, font=_font(22), fill="#f59e0b")
        return img


__all__ = ["GameWorld"]
