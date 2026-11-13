"""Deterministic camera viewport and screen-reader description for playable grids.

This is a pure derived presentation adapter. It never changes authored source,
simulation state, save events or collision rules.
"""
from __future__ import annotations

from dataclasses import dataclass

from .flgb_gameplay_runtime import GameplayContractError
from .offline_grid_campaign import Session

MAX_VIEW = 64
MIN_VIEW = 3


def _size(value: int, name: str) -> int:
    if type(value) is not int or not MIN_VIEW <= value <= MAX_VIEW:
        raise GameplayContractError("invalid " + name)
    return value


@dataclass(frozen=True)
class GameViewport:
    origin_x: int
    origin_y: int
    width: int
    height: int
    player_x: int
    player_y: int
    rows: tuple[str, ...]
    description: str
    visible_objects: tuple[str, ...]

    def render(self) -> str:
        return "\n".join(self.rows)

    def record(self) -> dict[str, object]:
        return {
            "origin": [self.origin_x, self.origin_y],
            "size": [self.width, self.height],
            "player": [self.player_x, self.player_y],
            "rows": list(self.rows),
            "description": self.description,
            "visible_objects": list(self.visible_objects),
        }


def viewport(session: Session, width: int = 11, height: int = 9) -> GameViewport:
    """Camera follows the player, clamps at map edges and labels visible actors."""
    if not isinstance(session, Session):
        raise GameplayContractError("invalid canonical campaign session")
    _size(width, "viewport width")
    _size(height, "viewport height")
    source = session.campaign.spec
    full_width = len(source["rows"][0])
    full_height = len(source["rows"])
    view_width = min(width, full_width)
    view_height = min(height, full_height)
    left = min(max(0, session.x - view_width // 2), full_width - view_width)
    top = min(max(0, session.y - view_height // 2), full_height - view_height)
    rendered = session.render().splitlines()
    rows = tuple(row[left:left + view_width]
                 for row in rendered[top:top + view_height])
    if len(rows) != view_height or any(len(row) != view_width for row in rows):
        raise GameplayContractError("noncanonical camera crop")
    if rows[session.y - top][session.x - left] != "@":
        raise GameplayContractError("player not visible in camera")

    visible = []
    enemies = dict(session.enemies)
    for actor in source["objects"]:
        x, y = actor["x"], actor["y"]
        if not (left <= x < left + view_width and top <= y < top + view_height):
            continue
        if actor["kind"] == "item" and actor["id"] in session.inventory:
            continue
        if actor["kind"] == "enemy" and enemies.get(actor["id"], 0) <= 0:
            continue
        visible.append((actor["id"], actor["kind"], x, y))
    visible.sort()
    object_labels = tuple(
        f"{kind} {identifier} at {x},{y}"
        for identifier, kind, x, y in visible
    )
    tile = source["rows"][session.y][session.x]
    tile_name = {"#": "wall", ".": "floor", "S": "start", "G": "goal"}[tile]
    status = (
        f"Player at {session.x},{session.y} on {tile_name}; "
        f"health {session.health}; tick {session.tick}; "
        f"ending {session.ending or 'in progress'}; "
        f"visible: {', '.join(object_labels) if object_labels else 'none'}."
    )
    return GameViewport(
        left, top, view_width, view_height, session.x, session.y,
        rows, status, object_labels,
    )
