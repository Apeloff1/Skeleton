"""Moving-boundary shoreline, 3D collision displacement, and coastal terrain journal.

The shallow-water update is ``advance_liquid`` from the existing conservative
solver. This module only relocates liquid that a solid shoreline or a 3D
obstacle occupies. Displaced volume is added back onto receiver cells, so the
step does not delete water.

Volume identity after the solver residual and the redistribution is:

    abs(final_volume_m3 - initial_volume_m3) <= VOLUME_CONSERVATION_EPSILON_M3

``VOLUME_CONSERVATION_EPSILON_M3`` is 1e-7 cubic metres. That bound covers
binary roundoff in the closed four-neighbor flux plus the last-cell remainder
used to keep the relocated sum equal to the displaced sum. A deleted cell of
water is orders of magnitude larger and fails the bound.

Cell depth stores volume divided by the full cell area. A partially flooded
shore cell therefore keeps one depth number, not a wet/dry sub-grid. Fully
solid cells are not receivers and finish the step dry. Coastal bed elevations
are stored in a content-addressed journal and restored by digest, not by wall
clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Sequence

from skeleton.jeeves.game_frontier_ecosystem import (
    EcosystemError,
    LiquidGrid,
    advance_liquid,
)


VOLUME_CONSERVATION_EPSILON_M3 = 1e-7
_SCHEMA = "skeleton.frontier_body.coastal_terrain_journal.v1"
_GENESIS = "0" * 64


class ShorelineError(ValueError):
    """Rejected shoreline, obstacle, or coastal-journal step."""


def _finite(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise ShorelineError(f"{label} must be a real number")
    if not math.isfinite(value) or not lo <= float(value) <= hi:
        raise ShorelineError(f"{label} must be finite and inside [{lo}, {hi}]")
    return float(value)


def _canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload: object) -> str:
    return sha256(_canon(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CollisionBox:
    """Axis-aligned solid volume in the same metres as the liquid grid.

    The grid's x axis runs along columns, y along rows, and z upward from the
    bed. A box intersects a water column on the closed-open cell footprint
    ``[ix * cell, (ix + 1) * cell)``.
    """

    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __post_init__(self) -> None:
        mins = (self.min_x, self.min_y, self.min_z)
        maxs = (self.max_x, self.max_y, self.max_z)
        labels = ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z")
        values = tuple(_finite(v, name, -1e6, 1e6) for v, name in zip(mins + maxs, labels))
        object.__setattr__(self, "min_x", values[0])
        object.__setattr__(self, "min_y", values[1])
        object.__setattr__(self, "min_z", values[2])
        object.__setattr__(self, "max_x", values[3])
        object.__setattr__(self, "max_y", values[4])
        object.__setattr__(self, "max_z", values[5])
        if not (self.max_x > self.min_x and self.max_y > self.min_y and self.max_z > self.min_z):
            raise ShorelineError("collision volume must have positive extent")


@dataclass(frozen=True)
class CoastalTerrain:
    """Persistent bed. Water depth is not part of the terrain identity."""

    width: int
    height: int
    cell_size_m: float
    bed_elevation_m: tuple[float, ...]

    def __post_init__(self) -> None:
        _validate_shape(self.width, self.height, self.cell_size_m, self.bed_elevation_m, self.bed_elevation_m)
        for elevation in self.bed_elevation_m:
            _finite(elevation, "bed elevation", -100000, 100000)


@dataclass(frozen=True)
class CoastalLiquidStep:
    grid: LiquidGrid
    terrain: CoastalTerrain
    initial_volume_m3: float
    final_volume_m3: float
    displaced_volume_m3: float
    solver_residual_m3: float
    volume_error_m3: float
    shore_column: float
    obstacle_count: int
    epsilon_m3: float = VOLUME_CONSERVATION_EPSILON_M3


@dataclass(frozen=True)
class CoastalJournalEntry:
    game_time_s: float
    terrain: CoastalTerrain
    prior_digest: str
    digest: str


@dataclass(frozen=True)
class CoastalJournal:
    entries: tuple[CoastalJournalEntry, ...] = ()


def _validate_shape(
    width: object,
    height: object,
    cell_size_m: object,
    bed: Sequence[float],
    depth: Sequence[float],
) -> None:
    if type(width) is not int or type(height) is not int or isinstance(width, bool) or isinstance(height, bool):
        raise ShorelineError("grid dimensions must be integers")
    if not (1 <= width <= 64 and 1 <= height <= 64):
        raise ShorelineError("grid dimensions require 1..64")
    _finite(cell_size_m, "cell_size_m", 0.01, 10000)
    count = width * height
    if len(bed) != count or len(depth) != count:
        raise ShorelineError("bed and water arrays must cover every cell")


def _land_fraction(column: int, shore_column: float) -> float:
    """Fraction of a column occupied by land that advances from x = 0."""

    if shore_column <= column:
        return 0.0
    if shore_column >= column + 1:
        return 1.0
    return shore_column - column


def _distribute(volumes: list[float], receivers: Sequence[int], displaced: float) -> None:
    """Add ``displaced`` across receivers. The last cell absorbs the remainder.

    Successive subtraction leaves the final portion equal to whatever volume
    was not yet assigned, so the added sum matches ``displaced`` to machine
    precision rather than ``n * (displaced / n)``.
    """

    if displaced == 0.0:
        return
    if not receivers:
        raise ShorelineError("no open cell can receive displaced liquid")
    remaining = displaced
    last = len(receivers) - 1
    share = displaced / len(receivers)
    for index, cell in enumerate(receivers):
        portion = remaining if index == last else share
        volumes[cell] += portion
        if index != last:
            remaining -= portion


def _obstacle_volume(
    column: int,
    row: int,
    *,
    width: int,
    cell_size_m: float,
    bed: float,
    depth: float,
    obstacles: tuple[CollisionBox, ...],
) -> float:
    if depth <= 0.0 or not obstacles:
        return 0.0
    x0 = column * cell_size_m
    x1 = x0 + cell_size_m
    y0 = row * cell_size_m
    y1 = y0 + cell_size_m
    z0 = bed
    z1 = bed + depth
    available = depth * cell_size_m * cell_size_m
    taken = 0.0
    for box in obstacles:
        overlap_x = min(x1, box.max_x) - max(x0, box.min_x)
        overlap_y = min(y1, box.max_y) - max(y0, box.min_y)
        overlap_z = min(z1, box.max_z) - max(z0, box.min_z)
        if overlap_x > 0.0 and overlap_y > 0.0 and overlap_z > 0.0:
            taken += overlap_x * overlap_y * overlap_z
            if taken >= available:
                return available
    return min(taken, available)


def _project_boundaries(
    grid: LiquidGrid,
    shore_column: float,
    obstacles: tuple[CollisionBox, ...],
) -> tuple[LiquidGrid, float]:
    area = grid.cell_size_m ** 2
    volumes = [depth * area for depth in grid.water_depth_m]
    fractions = [
        _land_fraction(index % grid.width, shore_column) for index in range(len(volumes))
    ]
    displaced = 0.0
    receivers = []
    for index, fraction in enumerate(fractions):
        take = volumes[index] * fraction
        volumes[index] -= take
        displaced += take
        if fraction < 1.0:
            receivers.append(index)
    _distribute(volumes, receivers, displaced)

    obstacle_takes = []
    obstacle_displaced = 0.0
    for index, volume in enumerate(volumes):
        column = index % grid.width
        row = index // grid.width
        depth = volume / area
        take = _obstacle_volume(
            column,
            row,
            width=grid.width,
            cell_size_m=grid.cell_size_m,
            bed=grid.bed_elevation_m[index],
            depth=depth,
            obstacles=obstacles,
        )
        take = min(take, volumes[index])
        volumes[index] -= take
        obstacle_displaced += take
        obstacle_takes.append(take)
    if obstacle_displaced > 0.0:
        free = [
            index
            for index, take in enumerate(obstacle_takes)
            if take == 0.0 and fractions[index] < 1.0
        ]
        if not free:
            open_cells = [index for index, fraction in enumerate(fractions) if fraction < 1.0]
            open_cells.sort(key=lambda index: (obstacle_takes[index], index))
            free = open_cells[:1]
        _distribute(volumes, free, obstacle_displaced)
        displaced += obstacle_displaced

    depths = []
    for volume in volumes:
        depth = volume / area
        if depth < 0.0:
            if depth < -1e-9:
                raise ShorelineError("boundary projection produced a negative water column")
            depth = 0.0
        _finite(depth, "projected water depth", 0, 10000)
        depths.append(depth)
    projected = LiquidGrid(
        grid.width,
        grid.height,
        grid.cell_size_m,
        grid.bed_elevation_m,
        tuple(depths),
    )
    return projected, displaced


def step_coastal_liquid(
    *,
    shore_column: float,
    delta_s: float,
    grid: LiquidGrid | None = None,
    width: int | None = None,
    height: int | None = None,
    cell_size_m: float | None = None,
    bed_elevation_m: Sequence[float] | None = None,
    water_depth_m: Sequence[float] | None = None,
    obstacles: tuple[CollisionBox, ...] | list[CollisionBox] = (),
) -> CoastalLiquidStep:
    """Advance the conservative solver, then enforce the moving shoreline.

    The flux step runs with no rain and no evaporation. Solid land and 3D
    obstacles afterwards push the occupied water onto open cells. Passing a
    negative cell size or a NaN bed/water/obstacle height rejects the step
    before any grid is updated.
    """

    if grid is not None:
        if not isinstance(grid, LiquidGrid):
            raise ShorelineError("grid must be a LiquidGrid from the conservative solver")
        if any(value is not None for value in (width, height, cell_size_m, bed_elevation_m, water_depth_m)):
            raise ShorelineError("pass either a liquid grid or raw columns, not both")
        width = grid.width
        height = grid.height
        cell_size_m = grid.cell_size_m
        bed_elevation_m = grid.bed_elevation_m
        water_depth_m = grid.water_depth_m
    if bed_elevation_m is None or water_depth_m is None or width is None or height is None or cell_size_m is None:
        raise ShorelineError("shoreline step requires a grid or complete raw columns")
    _validate_shape(width, height, cell_size_m, bed_elevation_m, water_depth_m)
    beds = tuple(_finite(value, "bed elevation", -100000, 100000) for value in bed_elevation_m)
    depths = tuple(_finite(value, "water depth", 0, 10000) for value in water_depth_m)
    shore = _finite(shore_column, "shore_column", 0, width)
    step_seconds = _finite(delta_s, "delta_s", 0, 60)
    if isinstance(obstacles, list):
        obstacles = tuple(obstacles)
    if type(obstacles) is not tuple or any(not isinstance(box, CollisionBox) for box in obstacles):
        raise ShorelineError("obstacles must be collision volumes")
    if len(obstacles) > 256:
        raise ShorelineError("obstacle count exceeds the shoreline step budget")
    try:
        source = LiquidGrid(width, height, cell_size_m, beds, depths)
    except EcosystemError as exc:
        raise ShorelineError(str(exc)) from exc
    initial = source.volume_m3
    solved = advance_liquid(source, delta_s=step_seconds, rain_mm_h=0, evaporation_mm_h=0)
    projected, displaced = _project_boundaries(solved.grid, shore, obstacles)
    final = projected.volume_m3
    error = abs(final - initial)
    if error > VOLUME_CONSERVATION_EPSILON_M3:
        raise ShorelineError(
            f"liquid volume changed by {error} m^3, outside {VOLUME_CONSERVATION_EPSILON_M3}"
        )
    terrain = CoastalTerrain(width, height, cell_size_m, beds)
    return CoastalLiquidStep(
        projected,
        terrain,
        initial,
        final,
        displaced,
        solved.mass_residual_m3,
        error,
        shore,
        len(obstacles),
    )


def _terrain_payload(terrain: CoastalTerrain, game_time_s: float, prior_digest: str) -> dict:
    return {
        "schema": _SCHEMA,
        "game_time_s": game_time_s,
        "width": terrain.width,
        "height": terrain.height,
        "cell_size_m": terrain.cell_size_m,
        "bed_elevation_m": list(terrain.bed_elevation_m),
        "prior_digest": prior_digest,
    }


def commit_coastal_terrain(
    journal: CoastalJournal,
    terrain: CoastalTerrain,
    *,
    game_time_s: float,
) -> CoastalJournal:
    """Append one bed snapshot. Game time must move forward. Heights are finite."""

    if not isinstance(journal, CoastalJournal) or not isinstance(terrain, CoastalTerrain):
        raise ShorelineError("coastal journal commit requires typed terrain")
    when = _finite(game_time_s, "game_time_s", 0, 1e12)
    if journal.entries and when <= journal.entries[-1].game_time_s:
        raise ShorelineError("coastal journal time must advance")
    prior = journal.entries[-1].digest if journal.entries else _GENESIS
    payload = _terrain_payload(terrain, when, prior)
    entry = CoastalJournalEntry(when, terrain, prior, _digest(payload))
    return CoastalJournal(journal.entries + (entry,))


def dump_coastal_journal(journal: CoastalJournal) -> str:
    if not isinstance(journal, CoastalJournal):
        raise ShorelineError("coastal journal dump requires a journal")
    entries = []
    for entry in journal.entries:
        payload = _terrain_payload(entry.terrain, entry.game_time_s, entry.prior_digest)
        if _digest(payload) != entry.digest:
            raise ShorelineError("coastal journal entry digest does not match its bed")
        payload["digest"] = entry.digest
        entries.append(payload)
    return _canon({"schema": _SCHEMA, "entries": entries})


def load_coastal_journal(payload: str) -> CoastalJournal:
    """Restore bed elevations. A edited height or digest is rejected."""

    if type(payload) is not str or not payload:
        raise ShorelineError("coastal journal payload must be text")
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ShorelineError("coastal journal payload is not JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA or not isinstance(raw.get("entries"), list):
        raise ShorelineError("coastal journal schema mismatch")
    entries: list[CoastalJournalEntry] = []
    prior = _GENESIS
    for item in raw["entries"]:
        if not isinstance(item, dict):
            raise ShorelineError("coastal journal entry is not an object")
        try:
            terrain = CoastalTerrain(
                int(item["width"]),
                int(item["height"]),
                item["cell_size_m"],
                tuple(item["bed_elevation_m"]),
            )
            when = item["game_time_s"]
            claimed_prior = item["prior_digest"]
            claimed = item["digest"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ShorelineError("coastal journal entry is incomplete") from exc
        if claimed_prior != prior:
            raise ShorelineError("coastal journal prior digest broke the chain")
        expect = _digest(_terrain_payload(terrain, when, claimed_prior))
        if claimed != expect:
            raise ShorelineError("coastal journal digest mismatch")
        entries.append(CoastalJournalEntry(when, terrain, claimed_prior, claimed))
        prior = claimed
    return CoastalJournal(tuple(entries))
