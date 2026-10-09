"""Minimal native, offline, model-free 2D game preview using stdlib Tk.

A playable preview, not a compiled console cartridge or a final game engine.
The simulation is headless-testable and calls the exact admitted platformer
step primitive used by the deterministic capability graph. Tk is imported
only when a user opens the graphical preview; no network or model assets.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from skeleton.ai.runtime.gameplay_capabilities import (
    GameplayError, compile_level, generate_level, platformer_step,
)
from skeleton.ai.runtime.game_playability import check_game_playability
from skeleton.ai.runtime.game_project_capsule import verify_game_capsule

DEFAULT_SEED = 1729
TILE_PIXELS = 28
TICK_MS = 100
WIDTH = 18
HEIGHT = 12


@dataclass(frozen=True, slots=True)
class PreviewFrame:
    frame: int
    tiles: tuple[str, ...]
    avatar: tuple[int, int]
    goal: tuple[int, int]
    grounded: bool
    won: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "width": len(self.tiles[0]),
            "height": len(self.tiles),
            "tiles": list(self.tiles),
            "avatar": {"x": self.avatar[0], "y": self.avatar[1]},
            "goal": {"x": self.goal[0], "y": self.goal[1]},
            "grounded": self.grounded,
            "won": self.won,
            "model_inference_used": False,
            "new_training_examples": 0,
        }


class OfflineGamePreview:
    """A small deterministic game state, independently testable without Tk."""

    def __init__(
        self, seed: int = DEFAULT_SEED, *,
        project_tiles: list[str] | None = None,
    ) -> None:
        if project_tiles is None:
            generated = generate_level({
            "seed": seed, "width": WIDTH, "height": HEIGHT,
            "wall_percent": 22,
            })
        # Procedural overhead platforms vary with seed, but keep an
        # intentional full-height start shaft and clear ground corridor.
        # This permits a real platformer to reach the goal by descending
        # and walking right, rather than conflating grid reachability
        # with actual avatar reachability.
        if project_tiles is None:
            world = [list(row) for row in generated["tiles"]]
            for y in range(1, HEIGHT - 1):
                world[y][1] = "."
            for x in range(1, WIDTH - 1):
                world[HEIGHT - 2][x] = "."
            world[1][1] = "S"
            world[HEIGHT - 2][WIDTH - 2] = "G"
            self.tiles = tuple("".join(row) for row in world)
        else:
            if not isinstance(project_tiles, list):
                raise GameplayError("preview project must provide an explicit tile map")
            evidence = check_game_playability({
                "tiles": project_tiles, "max_frames": 96,
            })
            if evidence["status"] != "playable":
                raise GameplayError(
                    "imported level cannot be proven controllably playable"
                )
            self.tiles = tuple(project_tiles)
        self._compiled = compile_level({"tiles": list(self.tiles)})
        if not self._compiled["goal_reachable"]:
            raise GameplayError("preview generator produced an unreachable goal")
        self.avatar: dict[str, int] = {
            **self._compiled["spawn"], "vx": 0, "vy": 0,
        }
        self.frame = 0
        self.won = False

    def reset(self) -> PreviewFrame:
        self.avatar = {**self._compiled["spawn"], "vx": 0, "vy": 0}
        self.frame = 0
        self.won = False
        return self.snapshot()

    def snapshot(self) -> PreviewFrame:
        position = self._compiled["goal"]
        return PreviewFrame(
            frame=self.frame,
            tiles=self.tiles,
            avatar=(self.avatar["x"], self.avatar["y"]),
            goal=(position["x"], position["y"]),
            grounded=not (
                0 <= self.avatar["y"] + 1 < len(self.tiles)
                and self.tiles[self.avatar["y"] + 1][self.avatar["x"]] != "#"
            ),
            won=self.won,
        )

    def tick(self, *, left: bool = False, right: bool = False,
             jump: bool = False) -> PreviewFrame:
        if any(type(x) is not bool for x in (left, right, jump)):
            raise GameplayError("preview controls must be boolean")
        if self.won:
            return self.snapshot()
        outcome = platformer_step({
            "tiles": list(self.tiles), "avatar": self.avatar,
            "control": {"left": left, "right": right, "jump": jump},
        })
        self.avatar = outcome["avatar"]
        self.won = outcome["goal_reached"]
        self.frame += 1
        return self.snapshot()


def load_game_project(path: str | Path) -> list[str]:
    """Read only an explicitly selected, bounded, verified local capsule."""
    selected = Path(path).expanduser()
    if selected.is_symlink() or not selected.is_file():
        raise GameplayError("selected game project must be a local regular file")
    fd = os.open(selected, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 160 * 1024:
            raise GameplayError("selected game project exceeds read-only limit")
        raw = stream.read(160 * 1024 + 1)
    if len(raw) > 160 * 1024:
        raise GameplayError("selected game project exceeds read-only limit")
    def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise GameplayError("duplicate game project JSON field")
            result[key] = value
        return result
    try:
        project = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                GameplayError("nonfinite game project number")
            ),
        )
        verify_game_capsule(project)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GameplayError("game project failed hash, rights or schema verification") from exc
    return project["tilemap"]


def verify_game_preview(
    seed: int = DEFAULT_SEED, *,
    project_tiles: list[str] | None = None,
) -> dict[str, Any]:
    """Proof of headless replay suitable for an installed EXE CI gate.

    Instantiate and simulate two independent native preview states, compare
    complete frame-by-frame trajectories, prove bounds and that no training
    data/model was required. This does NOT verify an actual visible desktop.
    """
    # Distinct gameplay phases prove a player can descend the safe shaft,
    # walk along the lower corridor and finish a seeded generated map.
    if project_tiles is None:
        controls = [
            {"left": False, "right": i >= 12, "jump": False}
            for i in range(32)
        ]
    else:
        evidence = check_game_playability({
            "tiles": project_tiles, "max_frames": 96,
        })
        if evidence["status"] != "playable":
            raise GameplayError("imported game's controller proof is inconclusive")
        controls = evidence["controller_actions"]
    trajectories: list[list[dict[str, Any]]] = []
    for _ in range(2):
        game = OfflineGamePreview(seed=seed, project_tiles=project_tiles)
        frames = [game.snapshot().as_dict()]
        for control in controls:
            frame = game.tick(**control)
            frames.append(frame.as_dict())
            if frame.won:
                # Finished games stay terminal and do not generate extra
                # simulation frames or silently count an additional victory.
                break
        for frame in frames:
            avatar = frame["avatar"]
            if not (
                0 <= avatar["x"] < len(game.tiles[0])
                and 0 <= avatar["y"] < len(game.tiles)
                and game.tiles[avatar["y"]][avatar["x"]] != "#"
            ):
                raise GameplayError("game preview replay left legal world bounds")
        trajectories.append(frames)
    if trajectories[0] != trajectories[1]:
        raise GameplayError("game preview simulation is nondeterministic")
    if not trajectories[0][-1]["won"]:
        raise GameplayError("seeded game preview failed playable-goal acceptance")
    raw = json.dumps(
        trajectories[0], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return {
        "schema_version": "skeleton.app.offline_game_preview_check.v1",
        "seed": seed if project_tiles is None else None,
        "project_source": "verified_portable_capsule" if project_tiles is not None else "seeded_builtin",
        "frames_verified": len(trajectories[0]) - 1,
        "replay_sha256": hashlib.sha256(raw).hexdigest(),
        "replay_deterministic": True,
        "source_level_goal_reachable": True,
        "terminal_won": trajectories[0][-1]["won"],
        "native_display_opened": False,
        "installed_tk_display_verified": False,
        "model_inference_used": False,
        "training_examples_added": 0,
        "network_access_used": False,
    }


def run_game_preview(
    seed: int = DEFAULT_SEED, *,
    project_tiles: list[str] | None = None,
) -> int:
    """Open a real desktop preview; run only with explicit user request."""
    game = OfflineGamePreview(seed=seed, project_tiles=project_tiles)
    columns, rows = len(game.tiles[0]), len(game.tiles)
    # Tk is stdlib, but optional on Linux/headless systems; keep the CLI's
    # non-UI game operations fully usable without display libraries.
    try:
        import tkinter as tk
    except ImportError as exc:
        raise GameplayError("native Tk support is not installed") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise GameplayError("native desktop display is unavailable") from exc
    root.title("Skeleton - Offline Game Preview")
    root.resizable(False, False)
    canvas = tk.Canvas(
        root, width=columns * TILE_PIXELS,
        height=rows * TILE_PIXELS + 36,
        highlightthickness=0, background="#131a29",
    )
    canvas.pack()
    buttons: set[str] = set()
    active = True

    def key_down(event: Any) -> None:
        symbol = str(event.keysym).lower()
        if symbol in ("left", "a"):
            buttons.add("left")
        elif symbol in ("right", "d"):
            buttons.add("right")
        elif symbol in ("space", "up", "w"):
            buttons.add("jump")
        elif symbol == "r":
            game.reset()
        elif symbol == "escape":
            close()

    def key_up(event: Any) -> None:
        symbol = str(event.keysym).lower()
        for name, codes in (
            ("left", ("left", "a")),
            ("right", ("right", "d")),
            ("jump", ("space", "up", "w")),
        ):
            if symbol in codes:
                buttons.discard(name)

    def render(frame: PreviewFrame) -> None:
        canvas.delete("all")
        for y, row in enumerate(frame.tiles):
            for x, char in enumerate(row):
                if char == "#":
                    canvas.create_rectangle(
                        x * TILE_PIXELS, y * TILE_PIXELS,
                        (x + 1) * TILE_PIXELS, (y + 1) * TILE_PIXELS,
                        fill="#3e5778", outline="#243750",
                    )
                elif char == "G":
                    margin = 5
                    canvas.create_oval(
                        x * TILE_PIXELS + margin, y * TILE_PIXELS + margin,
                        (x + 1) * TILE_PIXELS - margin,
                        (y + 1) * TILE_PIXELS - margin,
                        fill="#d5b35f", outline="#f2dd8b", width=2,
                    )
        ax, ay = frame.avatar
        cx, cy = ax * TILE_PIXELS, ay * TILE_PIXELS
        canvas.create_oval(
            cx + 4, cy + 3, cx + TILE_PIXELS - 4, cy + TILE_PIXELS - 3,
            fill="#a1e2b6", outline="#4d9c7b", width=2,
        )
        canvas.create_oval(cx + 9, cy + 10, cx + 12, cy + 14, fill="#253b34")
        canvas.create_oval(cx + 17, cy + 10, cx + 20, cy + 14, fill="#253b34")
        message = (
            "Goal reached! Press R to restart"
            if frame.won
            else "A/D or arrows to move  |  Space to jump  |  R to reset  |  Esc to exit"
        )
        canvas.create_text(
            columns * TILE_PIXELS // 2, rows * TILE_PIXELS + 18,
            text=message, fill="#e3ecf4", font=("Arial", 9),
        )

    def close() -> None:
        nonlocal active
        active = False
        root.destroy()

    def pulse() -> None:
        if not active:
            return
        render(game.tick(
            left="left" in buttons, right="right" in buttons,
            jump="jump" in buttons,
        ))
        if active:
            root.after(TICK_MS, pulse)

    root.bind("<KeyPress>", key_down)
    root.bind("<KeyRelease>", key_up)
    root.protocol("WM_DELETE_WINDOW", close)
    render(game.snapshot())
    root.after(TICK_MS, pulse)
    root.focus_force()
    root.mainloop()
    return 0


__all__ = [
    "DEFAULT_SEED", "PreviewFrame", "OfflineGamePreview",
    "run_game_preview", "verify_game_preview", "load_game_project",
]
