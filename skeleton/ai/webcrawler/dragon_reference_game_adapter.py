"""Actual visual adapter for the canonical original grid-game simulator.

The policy sees RGB pixels only. It recognizes this adapter's documented tile
palette and plans from that visual observation, without reading a saved route
or the simulator's private state. This does not imply arbitrary-game vision.
"""
from __future__ import annotations

from collections import deque
from ..game_builder.playable_world import PlayableWorld, DIRECTIONS
from ..game_builder.playable_simulation import advance, initial_state
from .dragon_visual_play import PlayAction, VisualFrame


PALETTE = {"#": (30, 35, 45), ".": (85, 100, 90), "S": (255, 255, 255),
           "G": (90, 160, 250), "C": (255, 210, 50), "H": (230, 65, 75),
           "X": (180, 220, 255)}
REVERSE_PALETTE = {value: key for key, value in PALETTE.items()}


class ReferenceGameVisualAdapter:
    adapter_id = "skeleton-original-grid-rgb-v1"

    def __init__(self, world: PlayableWorld, *, authorized: bool):
        self.world = world
        self.artifact_digest = world.digest
        self.state = initial_state(world, authorized=authorized)
        self.sequence = 0
        self.inputs_released = False

    def capture(self) -> VisualFrame:
        level = self.world.levels[self.state.level_index]
        pixels = bytearray()
        for y, row in enumerate(level.rows):
            for x, tile in enumerate(row):
                if tile == "S" or (x, y) in self.state.collected:
                    tile = "."
                if (x, y) == (self.state.x, self.state.y):
                    tile = "X" if tile == "G" else "S"
                pixels.extend(PALETTE[tile])
        frame = VisualFrame(self.sequence, level.width, level.height,
            bytes(pixels), self.state.status != "playing")
        self.sequence += 1
        return frame

    def advance(self, action: PlayAction) -> None:
        if self.inputs_released:
            raise PermissionError("reference game input session already closed")
        if len(action.buttons) != 1:
            raise ValueError("reference game needs one directional action")
        button = next(iter(action.buttons))
        for _ in range(action.frames):
            self.state = advance(self.world, self.state, button, authorized=True)

    def release_inputs(self) -> None:
        self.inputs_released = True


def reference_visual_policy(frame: VisualFrame) -> PlayAction:
    """Solve the current visible collectible-and-exit map from RGB data."""
    rows = []
    for y in range(frame.height):
        line = []
        for x in range(frame.width):
            offset = (y*frame.width+x)*3
            pixel = tuple(frame.rgb[offset:offset+3])
            if pixel not in REVERSE_PALETTE:
                raise ValueError("unknown reference-adapter visual tile")
            line.append(REVERSE_PALETTE[pixel])
        rows.append("".join(line))
    route = _visible_route(tuple(rows))
    if not route:
        raise ValueError("no visible legal route to objective")
    return PlayAction(frozenset({route[0]}))


def _visible_route(rows: tuple[str, ...]) -> tuple[str, ...]:
    """Bounded BFS allowing already-collected objectives and goal occupancy."""
    if not 1 <= len(rows) <= 41 or not 1 <= len(rows[0]) <= 41:
        raise ValueError("visual path grid exceeds reference-game limits")
    starts = [(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c in "SX"]
    goals = [(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c in "GX"]
    items = [(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == "C"]
    if len(starts) != 1 or len(goals) != 1 or len(items) > 6:
        raise ValueError("visual objective set invalid")
    bits = {p: 1 << i for i, p in enumerate(items)}
    origin = (*starts[0], 0)
    queue = deque([origin])
    came = {origin: None}
    while queue:
        x, y, mask = node = queue.popleft()
        if (x, y) == goals[0] and mask == (1 << len(items))-1:
            route = []
            while came[node] is not None:
                node, action = came[node]
                route.append(action)
            return tuple(reversed(route))
        for action, dx, dy in DIRECTIONS:
            nx, ny = x+dx, y+dy
            if 0 <= ny < len(rows) and 0 <= nx < len(rows[0]) and rows[ny][nx] not in "#H":
                next_node = (nx, ny, mask | bits.get((nx, ny), 0))
                if next_node not in came:
                    came[next_node] = (node, action)
                    queue.append(next_node)
    raise ValueError("visible objectives cannot be reached safely")
