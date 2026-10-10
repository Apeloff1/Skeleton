"""Native enhanced homebrew Windows port player with true original hybrid rules.

Generates graphics *from source homebrew geometry* rather than using
copyrighted source-game assets. The baseline physics and winning route
are preserved. High-end Windows graphics and hybrid overlays are
optional and configurable; visual accessibility can override colors.
All code stays offline in Tk and verified model-free game runtimes.
"""
from __future__ import annotations

from typing import Any

from scripts.game.game_project import _read_json
from skeleton.ai.runtime.homebrew_porting import (
    HomebrewPortError, PortedHomebrewSession,
    verify_homebrew_port, verify_port_gameplay,
)

SIM_MS = 100
BALANCED_DRAW_MS = 66
ENHANCED_DRAW_MS = 33
CINEMATIC_DRAW_MS = 25


def open_native_homebrew_port(
    capsule_path: str,
    blueprint_path: str,
) -> int:
    """Load user-selected original game + verified Windows port blueprint."""
    capsule = _read_json(__import__("pathlib").Path(capsule_path))
    blueprint = _read_json(__import__("pathlib").Path(blueprint_path))
    verify_homebrew_port(capsule, blueprint)
    verify_port_gameplay(capsule, blueprint)
    session = PortedHomebrewSession(capsule, blueprint)

    try:
        import tkinter as tk
    except ImportError as exc:
        raise HomebrewPortError("native Windows/Tk rendering library unavailable") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise HomebrewPortError("native Windows game display unavailable") from exc
    root.title("Skeleton | Original Homebrew — Enhanced Windows Edition")
    root.resizable(False, False)
    game = session.game
    rows, cols = len(game.tiles), len(game.tiles[0])
    pixel = blueprint["scale"]
    viewport_w = min(960, cols * pixel)
    viewport_h = min(640, rows * pixel)
    hud_height = 50 if blueprint["hud"] else 24
    canvas = tk.Canvas(
        root, width=viewport_w, height=viewport_h + hud_height,
        background=blueprint["render"]["palette"][0],
        highlightthickness=0,
    )
    canvas.pack()
    keys: set[str] = set()
    running = True
    tick_number = 0
    animation_frame = 0
    since_tick = 0
    draw_ms = {
        "balanced": BALANCED_DRAW_MS,
        "enhanced": ENHANCED_DRAW_MS,
        "cinematic": CINEMATIC_DRAW_MS,
    }[blueprint["quality"]]
    # User can disable animation independent of gameplay timing.
    palette = tuple(blueprint["render"]["palette"])
    if blueprint["high_contrast"]:
        palette = ("#101010", "#ffffff", "#03ffcf", "#ffd966", "#d5d5d5")
    elif blueprint["colorblind_safe"]:
        palette = ("#0a2640", "#31688e", "#f8e465", "#e96b78", "#80bfd9")
    bg, walls, actor, goal_color, decorative = palette

    def bounds() -> tuple[int, int]:
        if cols * pixel <= viewport_w:
            camera_x = 0
        else:
            camera_x = max(
                0, min(cols * pixel - viewport_w,
                       game.avatar["x"] * pixel - viewport_w // 2),
            )
        if rows * pixel <= viewport_h:
            camera_y = 0
        else:
            camera_y = max(
                0, min(rows * pixel - viewport_h,
                       game.avatar["y"] * pixel - viewport_h // 2),
            )
        return camera_x, camera_y

    def render() -> None:
        canvas.delete("all")
        ox, oy = bounds()
        time = animation_frame if not blueprint["reduced_motion"] else 0
        w, h = viewport_w, viewport_h
        canvas.create_rectangle(0, 0, w, h, fill=bg, outline=bg)
        # Original procedural decoration is entirely geometry/seed based.
        # Motion reduced mode freezes the layers and discards parallax.
        for decoration in blueprint["render"]["ambient_decorations"]:
            px = decoration["x"] * pixel + pixel // 2 - ox
            py = decoration["y"] * pixel + pixel // 2 - oy
            if blueprint["render"]["parallax_enabled"]:
                py += (time // 9 + decoration["variant"] * 5) % 9 - 4
            if -8 <= px <= w + 8 and -8 <= py <= h + 8:
                width = 1 + decoration["variant"] % 2
                canvas.create_oval(px - width, py - width,
                                   px + width, py + width,
                                   fill=decorative, outline="")
        for gy, line in enumerate(game.tiles):
            y = gy * pixel - oy
            if y + pixel < 0 or y > h:
                continue
            for gx, material in enumerate(line):
                x = gx * pixel - ox
                if x + pixel < 0 or x > w:
                    continue
                if material == "#":
                    # Original collision grid retained while Windows builds
                    # original bevels and precision edges beyond retro
                    # monochrome/palette capabilities.
                    canvas.create_rectangle(
                        x, y, x + pixel, y + pixel,
                        fill=walls, outline=decorative if blueprint["quality"] != "balanced" else walls,
                    )
                    if blueprint["render"]["layered_tile_shading"]:
                        canvas.create_line(
                            x + 3, y + 3, x + pixel - 4, y + 3,
                            fill=decorative, width=2,
                        )
                        canvas.create_line(
                            x + 3, y + 3, x + 3, y + pixel - 4,
                            fill=decorative,
                        )
                elif material == "G":
                    center = (x + pixel // 2, y + pixel // 2)
                    r = max(4, pixel // 4)
                    if blueprint["render"]["soft_goal_glow"]:
                        for outer in (r + 9, r + 5, r + 2):
                            canvas.create_oval(
                                center[0] - outer, center[1] - outer,
                                center[0] + outer, center[1] + outer,
                                outline=goal_color, width=1,
                            )
                    canvas.create_polygon(
                        center[0], center[1] - r,
                        center[0] + r, center[1],
                        center[0], center[1] + r,
                        center[0] - r, center[1],
                        fill=goal_color, outline=decorative, width=2,
                    )
        # Hybrid collectibles are genuine machine-state objects: native
        # scores and keyquest win gate use exactly these positions.
        for item in session.pending:
            x, y = item
            cx, cy = x * pixel + pixel // 2 - ox, y * pixel + pixel // 2 - oy
            r = max(3, pixel // 6)
            if -r <= cx <= w + r and -r <= cy <= h + r:
                canvas.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill=goal_color, outline=actor, width=2,
                )
        ax, ay = game.avatar["x"], game.avatar["y"]
        x, y = ax * pixel - ox, ay * pixel - oy
        canvas.create_oval(
            x + pixel // 5, y + pixel // 8,
            x + pixel * 4 // 5, y + pixel * 7 // 8,
            fill=actor, outline=decorative, width=2,
        )
        eye = max(2, pixel // 12)
        for dx in (pixel * 2 // 5, pixel * 3 // 5):
            canvas.create_oval(
                x + dx - eye, y + pixel // 3 - eye,
                x + dx + eye, y + pixel // 3 + eye,
                fill=bg, outline=bg,
            )
        if blueprint["gameplay"]["exploration_fog"]:
            for gy, line in enumerate(game.tiles):
                for gx in range(len(line)):
                    if (gx, gy) in session.visited:
                        continue
                    x, y = gx * pixel - ox, gy * pixel - oy
                    if x + pixel < 0 or y + pixel < 0 or x > w or y > h:
                        continue
                    canvas.create_rectangle(x, y, x + pixel, y + pixel,
                                            fill=bg, outline=bg)
        if blueprint["hud"]:
            text = (
                f"ORIGINAL HOMEBREW  |  {blueprint['art_direction'].replace('_', ' ').title()}  "
                f"|  Frames {session.frames}  |  Score {session.score}  "
                f"|  Items {len(session.pending)}  |  Explored {len(session.visited)}"
            )
            canvas.create_text(
                w // 2, h + 13, text=text,
                fill=actor, font=("Arial", 10, "bold"),
            )
            finish = (
                "WIN! R = RESTART"
                if session.win else
                ("GOAL LOCKED — COLLECT ALL ORIGINAL KEYS"
                 if session.locked_goal_attempts > 0 and
                    blueprint["gameplay"]["keyquest_gate"] and session.pending
                 else "A/D or arrows move · Space jumps · R resets · Esc quits")
            )
            canvas.create_text(w // 2, h + 35, text=finish,
                               fill=goal_color, font=("Arial", 10))
        else:
            canvas.create_text(
                w // 2, h + 12,
                text="WIN!" if session.win else "Original homebrew / Esc quits",
                fill=actor,
            )

    def key_down(event: Any) -> None:
        nonlocal session, game
        code = str(event.keysym).lower()
        if code in ("left", "a"):
            keys.add("left")
        elif code in ("right", "d"):
            keys.add("right")
        elif code in ("up", "space", "w"):
            keys.add("jump")
        elif code == "r":
            session = PortedHomebrewSession(capsule, blueprint)
            game = session.game
            keys.clear()
        elif code == "escape":
            close()

    def key_up(event: Any) -> None:
        code = str(event.keysym).lower()
        for name, alternatives in (
            ("left", ("left", "a")),
            ("right", ("right", "d")),
            ("jump", ("space", "up", "w")),
        ):
            if code in alternatives:
                keys.discard(name)

    def close() -> None:
        nonlocal running
        running = False
        root.destroy()

    def pulse() -> None:
        nonlocal running, animation_frame, tick_number, since_tick
        if not running:
            return
        animation_frame += 1
        since_tick += draw_ms
        if since_tick >= SIM_MS:
            since_tick -= SIM_MS
            session.tick(
                left="left" in keys, right="right" in keys,
                jump="jump" in keys,
            )
            tick_number += 1
        render()
        if running:
            root.after(draw_ms, pulse)

    root.bind("<KeyPress>", key_down)
    root.bind("<KeyRelease>", key_up)
    root.protocol("WM_DELETE_WINDOW", close)
    render()
    root.after(draw_ms, pulse)
    root.focus_force()
    root.mainloop()
    return 0


__all__ = ["open_native_homebrew_port"]
