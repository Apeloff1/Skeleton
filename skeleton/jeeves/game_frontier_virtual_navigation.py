"""In-game GPS, surveying and map navigation. Never uses device coordinates.

Positions are measured in a fictional world's own ENU-like XYZ metres.
The "GPS" sources are authored virtual ranging beacons, not GNSS hardware;
latitude/longitude-style values are explicitly *fictional*. The canonical
game engine owns actual entity state and signed GDD owns story/realm rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import heapq
import json
import math
from typing import TYPE_CHECKING

from .game_frontier_production import Vec3

if TYPE_CHECKING:
    from .game_frontier_frame_coherence import FrameReceipt, GDDSource


class VirtualPositionError(ValueError):
    pass


def _number(value: float, name: str, low: float = -1e8,
            high: float = 1e8) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise VirtualPositionError(f"{name} must be bounded finite")
    return float(value)


def _norm(point: Vec3) -> float:
    return math.sqrt(point.dot(point))


def _position(point: Vec3) -> list[float]:
    if not isinstance(point, Vec3):
        raise VirtualPositionError("typed 3D game position required")
    return [_number(v, "coordinate") for v in (point.x, point.y, point.z)]


def _digest(value: object) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise VirtualPositionError("noncanonical world position evidence") from error
    return sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class GameMap:
    world_id: str
    realm_id: str
    width_tiles: int
    height_tiles: int
    tile_size_m: float
    origin: Vec3 = Vec3(0, 0, 0)
    north_rotation_deg: float = 0.
    blocked_tiles: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(v, str) or not 1 <= len(v) <= 128
               for v in (self.world_id, self.realm_id)):
            raise VirtualPositionError("fictional world and realm IDs required")
        if any(type(n) is not int or not 1 <= n <= 4096
               for n in (self.width_tiles, self.height_tiles)):
            raise VirtualPositionError("map dimensions must fit 4096 tiles")
        _number(self.tile_size_m, "tile size", .01, 1000)
        _number(self.north_rotation_deg, "map rotation", -360, 360)
        _position(self.origin)
        if len(self.blocked_tiles) > 65536 or len(set(self.blocked_tiles)) != len(self.blocked_tiles):
            raise VirtualPositionError("invalid or duplicated obstacle catalog")
        for x, y in self.blocked_tiles:
            if (type(x) is not int or type(y) is not int or
                not (0 <= x < self.width_tiles and 0 <= y < self.height_tiles)):
                raise VirtualPositionError("blocked tile outside world map")

    def grid(self, point: Vec3) -> tuple[int, int]:
        _position(point)
        diff = point - self.origin
        angle = math.radians(self.north_rotation_deg)
        east = diff.x * math.cos(angle) + diff.y * math.sin(angle)
        north = -diff.x * math.sin(angle) + diff.y * math.cos(angle)
        x, y = math.floor(east / self.tile_size_m), math.floor(north / self.tile_size_m)
        if not (0 <= x < self.width_tiles and 0 <= y < self.height_tiles):
            raise VirtualPositionError("entity outside fictional map")
        return x, y

    def tile_world(self, x: int, y: int, *, center: bool = True) -> Vec3:
        if any(type(k) is not int for k in (x, y)) or not (
            0 <= x < self.width_tiles and 0 <= y < self.height_tiles
        ):
            raise VirtualPositionError("invalid map tile")
        east = (x + (.5 if center else 0)) * self.tile_size_m
        north = (y + (.5 if center else 0)) * self.tile_size_m
        a = math.radians(self.north_rotation_deg)
        return self.origin + Vec3(
            east * math.cos(a) - north * math.sin(a),
            east * math.sin(a) + north * math.cos(a), 0)

    def fictional_coordinates(self, point: Vec3) -> tuple[float, float]:
        """Coordinates resemble lat/lon ONLY inside this fictional planet.

        No WGS84 relationship, IP lookup, Earth map, OS sensor or real location.
        """
        e, n, _ = _position(point - self.origin)
        radius = 6_371_008.8
        return math.degrees(n / radius), math.degrees(e / radius)

    def identity(self) -> str:
        return _digest({
            "world": self.world_id, "realm": self.realm_id,
            "width": self.width_tiles, "height": self.height_tiles,
            "tile_m": self.tile_size_m, "origin": _position(self.origin),
            "rotation": self.north_rotation_deg,
            "obstacles": self.blocked_tiles,
        })


@dataclass(frozen=True)
class VirtualBeacon:
    beacon_id: str
    position: Vec3
    uncertainty_m: float = .05
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.beacon_id or len(self.beacon_id) > 128:
            raise VirtualPositionError("virtual beacon identity required")
        _position(self.position)
        _number(self.uncertainty_m, "ranging uncertainty", .000001, 1000)
        if type(self.enabled) is not bool:
            raise VirtualPositionError("beacon enabled flag must be boolean")


@dataclass(frozen=True)
class VirtualRange:
    beacon_id: str
    measured_range_m: float
    uncertainty_m: float
    blocked: bool = False

    def __post_init__(self) -> None:
        if not self.beacon_id or len(self.beacon_id) > 128:
            raise VirtualPositionError("range source ID required")
        _number(self.measured_range_m, "range", 0, 1e8)
        _number(self.uncertainty_m, "range uncertainty", .000001, 1000)
        if type(self.blocked) is not bool:
            raise VirtualPositionError("blocked signal flag must be boolean")


@dataclass(frozen=True)
class VirtualFix:
    position: Vec3
    rms_range_error_m: float
    horizontal_uncertainty_m: float
    vertical_uncertainty_m: float
    used_beacons: tuple[str, ...]
    method: str = "fictional_3d_ranging_multilateration"
    authority: str = "virtual_game_only_no_device_location"

    def __post_init__(self) -> None:
        _position(self.position)


def simulated_ranges(true_world_position: Vec3,
                     beacons: tuple[VirtualBeacon, ...],
                     *, noise_seed: int = 0,
                     blocked_ids: frozenset[str] = frozenset()) -> tuple[VirtualRange, ...]:
    if type(noise_seed) is not int or not 0 <= noise_seed < 2**63:
        raise VirtualPositionError("bounded deterministic game noise seed required")
    _position(true_world_position)
    if len(beacons) > 64 or len({b.beacon_id for b in beacons}) != len(beacons):
        raise VirtualPositionError("ambiguous game beacon catalog")
    ranges = []
    for beacon in beacons:
        if not beacon.enabled:
            continue
        raw = sha256(f"{noise_seed}:{beacon.beacon_id}".encode()).digest()
        signed = int.from_bytes(raw[:8], "big") / (2**64 - 1) * 2 - 1
        actual = _norm(true_world_position - beacon.position)
        # Bounded deterministic simulation error, not a physical GNSS noise model.
        measured = max(0., actual + signed * beacon.uncertainty_m)
        ranges.append(VirtualRange(beacon.beacon_id, measured,
                                   beacon.uncertainty_m,
                                   blocked=beacon.beacon_id in blocked_ids))
    return tuple(ranges)


def _solve3(matrix: list[list[float]], rhs: list[float]) -> tuple[tuple[float, float, float], float]:
    """Independent pivoted Gaussian elimination; reject singular constellations."""
    rows = [list(row) + [rhs[i]] for i, row in enumerate(matrix)]
    top = max(abs(v) for row in matrix for v in row)
    if top <= 1e-18:
        raise VirtualPositionError("no geometric diversity in beacon constellation")
    smallest = top
    for i in range(3):
        pivot = max(range(i, 3), key=lambda r: abs(rows[r][i]))
        scale = abs(rows[pivot][i])
        if scale < top * 1e-10:
            raise VirtualPositionError("coplanar or ill-conditioned beacon geometry")
        smallest = min(smallest, scale)
        rows[i], rows[pivot] = rows[pivot], rows[i]
        divisor = rows[i][i]
        for j in range(i, 4):
            rows[i][j] /= divisor
        for k in range(3):
            if k == i:
                continue
            multiplier = rows[k][i]
            for j in range(i, 4):
                rows[k][j] -= multiplier * rows[i][j]
    return (rows[0][3], rows[1][3], rows[2][3]), top / smallest


def solve_virtual_gps(beacons: tuple[VirtualBeacon, ...],
                      ranges: tuple[VirtualRange, ...],
                      *, maximum_residual_m: float = 5.) -> VirtualFix:
    """Solve XYZ using 4+ noncoplanar virtual ranging stations.

    Difference-of-squared-distance least squares, then independent absolute
    range residuals. Returns NO actual-device GNSS or WGS84 information.
    """
    _number(maximum_residual_m, "maximum residual", .001, 1000)
    if len(beacons) > 64 or len(ranges) > 64:
        raise VirtualPositionError("beacon budget exceeded")
    catalog = {b.beacon_id: b for b in beacons}
    if len(catalog) != len(beacons) or len({r.beacon_id for r in ranges}) != len(ranges):
        raise VirtualPositionError("duplicate game beacon measurements")
    if any(r.beacon_id not in catalog for r in ranges):
        raise VirtualPositionError("range references nonexistent beacon")
    active = [(catalog[r.beacon_id], r) for r in ranges
              if not r.blocked and catalog[r.beacon_id].enabled]
    if len(active) < 4:
        raise VirtualPositionError("3D fictional GPS needs four visible beacons")
    anchor, origin = active[0]
    p0, r0 = origin.position, anchor.measured_range_m
    matrix = [[0.] * 3 for _ in range(3)]
    vector = [0.] * 3
    for beacon, signal in active[1:]:
        delta = beacon.position - p0
        co = [2 * delta.x, 2 * delta.y, 2 * delta.z]
        target = (delta.dot(delta) - signal.measured_range_m**2
                  + r0**2)
        weight = 1 / max(.001, signal.uncertainty_m**2 + anchor.uncertainty_m**2)
        for i in range(3):
            vector[i] += weight * co[i] * target
            for j in range(3):
                matrix[i][j] += weight * co[i] * co[j]
    xyz, condition = _solve3(matrix, vector)
    solution = p0 + Vec3(*xyz)
    _position(solution)
    residual = math.sqrt(sum(
        (_norm(solution - b.position) - r.measured_range_m)**2
        for b, r in active) / len(active))
    if residual > maximum_residual_m:
        raise VirtualPositionError("simulated beacon ranges do not describe one location")
    bound = max(residual, max(r.uncertainty_m for _, r in active)) * max(1, math.sqrt(condition))
    if not math.isfinite(bound) or bound > 100000:
        raise VirtualPositionError("virtual fix uncertainty too high")
    return VirtualFix(solution, residual, bound, bound,
                      tuple(b.beacon_id for b, _ in active))


@dataclass(frozen=True)
class VirtualSurveyControl:
    control_id: str
    position: Vec3
    gdd_verified: bool = True

    def __post_init__(self) -> None:
        if not self.control_id or len(self.control_id) > 128 or self.gdd_verified is not True:
            raise VirtualPositionError("only approved fictional survey stations permitted")
        _position(self.position)


@dataclass(frozen=True)
class VirtualSurveySighting:
    control_id: str
    bearing_from_station_deg: float
    angular_error_deg: float = .1
    elevation_deg: float | None = None

    def __post_init__(self) -> None:
        if not self.control_id or len(self.control_id) > 128:
            raise VirtualPositionError("survey sighting ID required")
        _number(self.bearing_from_station_deg, "virtual bearing", 0, 360)
        _number(self.angular_error_deg, "bearing error", .000001, 20)
        if self.elevation_deg is not None:
            _number(self.elevation_deg, "elevation angle", -89, 89)


@dataclass(frozen=True)
class VirtualSurveyFix:
    position: Vec3
    rms_cross_track_m: float
    uncertainty_m: float
    control_ids: tuple[str, ...]
    altitude_resolved: bool
    authority: str = "fictional_survey_not_geodetic_certification"


def solve_virtual_survey(controls: tuple[VirtualSurveyControl, ...],
                         sightings: tuple[VirtualSurveySighting, ...],
                         *, maximum_residual_m: float = 5.) -> VirtualSurveyFix:
    _number(maximum_residual_m, "survey tolerance", .001, 1000)
    if not 2 <= len(sightings) <= 32 or len(controls) > 64:
        raise VirtualPositionError("virtual survey requires at least two stations")
    by_id = {c.control_id: c for c in controls}
    if (len(by_id) != len(controls) or
        len({s.control_id for s in sightings}) != len(sightings) or
        any(s.control_id not in by_id for s in sightings)):
        raise VirtualPositionError("duplicate or unknown survey controls")
    aa = ab = bb = ax = ay = 0.
    rows = []
    for sight in sightings:
        point = by_id[sight.control_id].position
        direction = math.radians(sight.bearing_from_station_deg)
        u, v = math.cos(direction), -math.sin(direction)
        offset = u * point.x + v * point.y
        weight = 1 / max(.0001, math.radians(sight.angular_error_deg)**2)
        aa += weight*u*u
        ab += weight*u*v
        bb += weight*v*v
        ax += weight*u*offset
        ay += weight*v*offset
        rows.append((u, v, offset, sight, point))
    determinant = aa*bb - ab*ab
    if determinant <= 0 or determinant / max(aa*bb, .001) < .005:
        raise VirtualPositionError("parallel virtual survey bearings")
    x, y = (ax*bb - ay*ab)/determinant, (ay*aa - ax*ab)/determinant
    rms = math.sqrt(sum((u*x+v*y-p)**2 for u,v,p,_,_ in rows)/len(rows))
    if rms > maximum_residual_m:
        raise VirtualPositionError("survey bearing residuals disagree")
    altitudes = []
    for _, _, _, sight, station in rows:
        if sight.elevation_deg is not None:
            horizontal = math.hypot(x-station.x, y-station.y)
            altitudes.append(station.z + horizontal*math.tan(
                math.radians(sight.elevation_deg)))
    altitude = (sum(altitudes)/len(altitudes) if altitudes
                else sum(s.position.z for s in controls)/len(controls))
    if altitudes and max(abs(z-altitude) for z in altitudes) > maximum_residual_m:
        raise VirtualPositionError("survey vertical observations disagree")
    uncertainty = max(rms, max(
        math.hypot(x-p.x, y-p.y)*math.radians(s.angular_error_deg)
        for _, _, _, s, p in rows))
    return VirtualSurveyFix(Vec3(x,y,altitude),rms,uncertainty,
                            tuple(s.control_id for s in sightings),
                            bool(altitudes))


@dataclass(frozen=True)
class VirtualRoute:
    tiles: tuple[tuple[int,int], ...]
    length_m: float
    destination: tuple[int,int]
    visited_nodes: int
    authority: str = "fictional_walkable_map_only"


def map_route(world: GameMap, start: tuple[int,int],
              goal: tuple[int,int], *,
              max_expansions: int = 65536) -> VirtualRoute:
    """Deterministic A* on authored 4-way map. No collision/physics authority."""
    if type(max_expansions) is not int or not 1 <= max_expansions <= 65536:
        raise VirtualPositionError("bounded route search required")
    for tile in (start,goal):
        world.tile_world(*tile)
    blocked = set(world.blocked_tiles)
    if start in blocked or goal in blocked:
        raise VirtualPositionError("map start or destination blocked")
    frontier = [(abs(start[0]-goal[0])+abs(start[1]-goal[1]),0,start)]
    cost = {start: 0}
    came = {}
    visits = 0
    while frontier and visits < max_expansions:
        _, d, node = heapq.heappop(frontier)
        if d != cost.get(node):
            continue
        visits += 1
        if node == goal:
            path = [node]
            while path[-1] != start:
                path.append(came[path[-1]])
            path.reverse()
            return VirtualRoute(tuple(path),(len(path)-1)*world.tile_size_m,goal,visits)
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
            nx,ny = node[0]+dx,node[1]+dy
            p = (nx,ny)
            if not (0 <= nx < world.width_tiles and 0 <= ny < world.height_tiles):
                continue
            if p in blocked or d+1 >= cost.get(p,math.inf):
                continue
            cost[p] = d+1
            came[p] = node
            heapq.heappush(frontier,(d+1+abs(nx-goal[0])+abs(ny-goal[1]),d+1,p))
    raise VirtualPositionError("no accessible fictional map route in search budget")


@dataclass(frozen=True)
class VirtualNavigationRequest:
    world: GameMap
    actor_id: str
    actor_truth: Vec3
    beacons: tuple[VirtualBeacon,...]
    noise_seed: int = 0
    blocked_beacons: frozenset[str] = frozenset()
    controls: tuple[VirtualSurveyControl,...] = ()
    sightings: tuple[VirtualSurveySighting,...] = ()
    destination_tile: tuple[int,int] | None = None

    def __post_init__(self) -> None:
        if not self.actor_id or len(self.actor_id)>128:
            raise VirtualPositionError("virtual actor identity required")
        self.world.grid(self.actor_truth)
        if bool(self.controls) != bool(self.sightings):
            raise VirtualPositionError("virtual survey stations/sightings must be paired")


def compose_virtual_navigation(
    request: VirtualNavigationRequest, *,
    frame: "FrameReceipt | None" = None,
    gdd: "GDDSource | None" = None,
    previous_frame: "FrameReceipt | None" = None,
) -> dict:
    """In-world GPS plus independent survey and checked frame/GDD attachment.

    Game-map XYZ may be shown to the player. Never source OS GPS or Earth
    WGS84. If frame provided, its actor must match actual game entity truth.
    """
    if not isinstance(request,VirtualNavigationRequest):
        raise VirtualPositionError("typed game navigation request required")
    if (frame is None) != (gdd is None):
        raise VirtualPositionError("frame and verified GDD must be supplied together")
    if frame is not None:
        from .game_frontier_frame_coherence import verify_frame
        a,b = verify_frame(frame,gdd,previous=previous_frame)
        if not a or not b or gdd.project_id != request.world.world_id:
            raise VirtualPositionError("invalid frame or mismatched fictional GDD")
        actors = [o for chunk in frame.chunks for o in chunk.objects
                  if o.entity_id == request.actor_id]
        if len(actors) != 1 or _norm(actors[0].position-request.actor_truth) > 1e-6:
            raise VirtualPositionError("virtual GPS actor diverged from verified frame")
    ranges = simulated_ranges(request.actor_truth,request.beacons,
                              noise_seed=request.noise_seed,
                              blocked_ids=request.blocked_beacons)
    fix = solve_virtual_gps(request.beacons,ranges)
    survey = solve_virtual_survey(request.controls,request.sightings) if request.controls else None
    survey_separation = (_norm(fix.position-survey.position) if survey else None)
    survey_tolerance = (
        3*math.hypot(fix.horizontal_uncertainty_m,survey.uncertainty_m)
        if survey else None)
    if survey and survey.altitude_resolved:
        survey_separation = _norm(fix.position-survey.position)
    elif survey:
        survey_separation = math.hypot(fix.position.x-survey.position.x,
                                      fix.position.y-survey.position.y)
    if survey and survey_separation > survey_tolerance:
        raise VirtualPositionError("independent fictional survey and GPS disagree")
    if _norm(fix.position-request.actor_truth) > max(
        5., 3*fix.horizontal_uncertainty_m):
        raise VirtualPositionError("simulated GPS diverged from game state")
    cell = request.world.grid(fix.position)
    truth_cell = request.world.grid(request.actor_truth)
    if cell != truth_cell and _norm(fix.position-request.actor_truth) > request.world.tile_size_m*.5:
        raise VirtualPositionError("virtual GPS moved actor outside coherent map tile")
    route = (map_route(request.world,truth_cell,request.destination_tile)
             if request.destination_tile is not None else None)
    lat,lon = request.world.fictional_coordinates(fix.position)
    evidence = {
        "schema":"skeleton.game.virtual_map_gps.v1",
        "world_id":request.world.world_id,"realm_id":request.world.realm_id,
        "world_map_digest":request.world.identity(),
        "map_width_tiles":request.world.width_tiles,
        "map_height_tiles":request.world.height_tiles,
        "tile_size_m":request.world.tile_size_m,
        "source":"fictional_simulated_beacons_no_device_gps",
        "actor_id":request.actor_id,
        "world_xyz_m":_position(fix.position),
        "map_tile_xy":list(cell),
        "fictional_latitude_deg":lat,"fictional_longitude_deg":lon,
        "fictional_datum":"planet_local_enu_not_earth_wgs84",
        "horizontal_uncertainty_m":fix.horizontal_uncertainty_m,
        "vertical_uncertainty_m":fix.vertical_uncertainty_m,
        "range_residual_m":fix.rms_range_error_m,
        "beacon_count":len(fix.used_beacons),
        "survey":({
            "world_xyz_m":_position(survey.position),
            "altitude_resolved":survey.altitude_resolved,
            "uncertainty_m":survey.uncertainty_m,
            "rms_m":survey.rms_cross_track_m,
            "separation_m":survey_separation,
            "tolerance_m":survey_tolerance,
            "consistent":True,
            "controls":list(survey.control_ids),
        } if survey else None),
        "route":({
            "tiles":[list(x) for x in route.tiles],
            "length_m":route.length_m,
            "destination_tile":list(route.destination),
            "visited_nodes":route.visited_nodes,
        } if route else None),
        "frame_receipt_digest":frame.receipt_digest if frame else None,
        "gdd_digest":gdd.source_digest if gdd else None,
        "double_verified":bool(frame is None or
            (frame.verifier_a_integrity and frame.verifier_b_coherence)),
        "device_location_used":False,
        "authority":"virtual_game_navigation_candidate_no_world_mutation",
    }
    evidence["receipt_digest"] = _digest(evidence)
    return evidence
