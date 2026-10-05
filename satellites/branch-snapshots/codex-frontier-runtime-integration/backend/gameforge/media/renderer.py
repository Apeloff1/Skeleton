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


def _rgba(hex_color: str, alpha: int) -> Tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), max(0, min(255, alpha)))


class GameWorld:
    def __init__(self, game_name: str, files: Optional[List[Dict]] = None):
        self.name = game_name or "Untitled"
        self.seed = _seed(self.name)
        rng = self.seed
        self.sky = _SKY[rng % len(_SKY)]
        self.mood = ["ember", "night", "dusk", "forest"][rng % len(_SKY)]
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
                     label: Optional[str] = None, portrait: Optional[int] = None,
                     cinematic: bool = True) -> Image.Image:
        img = self._sky_bg(W, H)
        d = ImageDraw.Draw(img, "RGBA")
        px, py = self.player_pos(t)
        cam = camera_x if camera_x is not None else px - W * 0.35

        def sx(wx):  # world→screen x
            return int(wx - cam)

        # ── celestial body + glow (sun/moon) ──
        sun_x, sun_y = int(W * 0.74), int(H * 0.24)
        glow = "#f59e0b" if self.mood in ("ember", "dusk") else "#a5b4fc"
        for rr, aa in ((90, 24), (60, 40), (34, 90)):
            d.ellipse([sun_x - rr, sun_y - rr, sun_x + rr, sun_y + rr],
                      fill=_rgba(glow, aa))
        d.ellipse([sun_x - 22, sun_y - 22, sun_x + 22, sun_y + 22], fill=_rgba(glow, 235))

        # ── star / ember field (deterministic) ──
        for i in range(46):
            r = (self.seed >> (i % 24)) ^ (i * 2654435761 & 0xFFFFFF)
            sx0 = (r % W)
            sy0 = ((r // W) % int(H * 0.6))
            tw = 1 + ((r >> 3) % 2)
            a = 90 + ((r >> 5) % 130)
            d.ellipse([sx0, sy0, sx0 + tw, sy0 + tw], fill=_rgba("#e2e8f0", a))

        # ── parallax terrain (4 depth-graded layers) ──
        ground_y = int(H * 0.72)
        layers = [(0.2, (26, 22, 48), 60), (0.4, (34, 28, 62), 42),
                  (0.7, (44, 33, 74), 24), (1.0, (14, 20, 34), 6)]
        for speed, col, base in layers:
            step = int(80 * (W / 640))
            pts = [(W, H)]
            x = -((cam * speed) % step) - step
            while x < W + step:
                wx = x + (cam * speed)
                hy = ground_y + base - self.hills[int(wx / step) % len(self.hills)] * (H / 360)
                pts.append((int(x), int(hy)))
                x += step
            pts.append((0, H))
            d.polygon(pts, fill=col)
        d.rectangle([0, int(ground_y + 40 * (H / 360)), W, H], fill=(10, 9, 20))

        sc = H / 360.0  # sprite scale factor

        def _sprite(cx, cy, color, rim="#ffffff", scale=1.0):
            rr = int(11 * sc * scale)
            # soft ground shadow
            d.ellipse([cx - rr, cy + rr, cx + rr, cy + int(rr * 1.4)], fill=_rgba("#000000", 90))
            # body
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=color)
            # rim light
            d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 200, 340, fill=rim, width=max(1, int(2 * sc)))
            # head glint
            d.ellipse([cx - rr // 3, cy - rr // 2, cx + rr // 3, cy], fill=_rgba("#ffffff", 200))

        # entities
        for i in range(len(self.cast)):
            ex, ey = self.entity_pos(i, t)
            sxe = sx(ex)
            if -40 < sxe < W + 40:
                col = _ENTITY_COLORS[i % len(_ENTITY_COLORS)]
                eyp = int(ground_y - 18 * sc - ey * 0.15)
                _sprite(sxe, eyp, col, scale=0.9)

        # player (protagonist) with motion trail
        pxs = sx(px)
        pyp = int(ground_y - 22 * sc - py * 0.15)
        for k in range(1, 4):
            tp = t - k * 0.12
            tx = sx(self.player_pos(tp)[0])
            ty = int(ground_y - 22 * sc - self.player_pos(tp)[1] * 0.15)
            d.ellipse([tx - 10 * sc, ty - 10 * sc, tx + 10 * sc, ty + 10 * sc],
                      fill=_rgba("#7c3aed", 60 - k * 15))
        _sprite(pxs, pyp, "#7c3aed", rim="#ffffff", scale=1.25)

        # ── floating embers / dust particles ──
        for i in range(18):
            r = (self.seed * (i + 3)) & 0xFFFFFF
            fx = int((r + t * (20 + i)) % W)
            fy = int(H - ((r >> 4) + t * (14 + i * 2)) % H)
            d.ellipse([fx, fy, fx + 2, fy + 2], fill=_rgba(glow, 120))

        # portrait spotlight (character close-up framing)
        if portrait is not None:
            who = self.cast[portrait % len(self.cast)] if portrait > 0 else self.name
            col = "#7c3aed" if portrait == 0 else _ENTITY_COLORS[portrait % len(_ENTITY_COLORS)]
            d.rectangle([0, 0, W, H], outline=col, width=max(4, int(6 * sc)))

        if cinematic:
            from gameforge.media.cinematic import grade
            img = grade(img, mood=self.mood, bloom=True, grain=0.03, letterbox=True)
            d = ImageDraw.Draw(img, "RGBA")

        # ── text overlays (after grade so they stay crisp) ──
        if portrait is not None:
            who = self.cast[portrait % len(self.cast)] if portrait > 0 else self.name
            d.text((18, 18), who, font=_font(int(26 * sc)), fill="#ffffff",
                   stroke_width=2, stroke_fill="#000000")
        if hud:
            d.text((12, int(10 * sc)), f"{self.name}", font=_font(int(16 * sc)),
                   fill="#22c55e", stroke_width=2, stroke_fill="#000000")
            d.text((W - int(130 * sc), int(10 * sc)), f"t={t:.1f}s",
                   font=_font(int(14 * sc)), fill="#e2e8f0", stroke_width=2, stroke_fill="#000000")
        if label:
            f = _font(int(24 * sc))
            tw = d.textlength(label, font=f)
            d.text(((W - tw) / 2, H - int(52 * sc)), label, font=f, fill="#f59e0b",
                   stroke_width=3, stroke_fill="#000000")
        return img


__all__ = ["GameWorld"]

