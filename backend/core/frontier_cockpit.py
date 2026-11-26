"""In-memory Galaxy Studio / Jeeves cockpit session for fictional navigation.

The session composes the frontier_nav minimap and survey authority with the
forge environmental-event ledger. A proposal does not change the save.
Device geolocation is not consulted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from skeleton.forge.game_frontier_event_authority import (
    CanonRules,
    EnvironmentalLedger,
    EventAuthorityError,
    QuestSpec,
    SaveState,
)
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger,
    RPGEventAction,
    RPGEventError,
    RPGEventPage,
)
from skeleton.frontier_nav.gps import (
    FICTIONAL_LAYER_KINDS,
    MINIMAP_ZOOMS,
    FictionalMapLayer,
    FictionalPortal,
    GPSRejected,
    MinimapCamera,
    follow_portal,
    jump_minimap_layer,
    minimap_viewport,
    opening_camera,
    pan_minimap,
    validate_fictional_portals,
    zoom_minimap,
)
from skeleton.frontier_nav.survey_approval import (
    FICTIONAL_DATUM,
    BaselineRecord,
    ControlStation,
    SightingRecord,
    SurveyAuthorityError,
    SurveyBook,
)

SERVER_KEY = b"frontier-cockpit-authority-key"
DEMO_WORLD = "meadow-realm"


class CockpitError(ValueError):
    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class CockpitWorld:
    world_id: str
    layers: tuple[FictionalMapLayer, ...]
    portals: tuple[FictionalPortal, ...]
    camera: MinimapCamera
    survey: SurveyBook
    ledger: EnvironmentalLedger
    last_fix: dict | None = None
    fixes: list[dict] = field(default_factory=list)


class FrontierCockpitService:
    def __init__(self) -> None:
        self._worlds: dict[str, CockpitWorld] = {}
        self._lock = Lock()

    def view(self, world_id: str) -> dict:
        with self._lock:
            return _public(self._require(world_id))

    def pan(self, world_id: str, dx: int, dy: int) -> dict:
        with self._lock:
            world = self._require(world_id)
            layer = _layer(world, world.camera.layer_id)
            try:
                world.camera = pan_minimap(world.camera, layer, dx, dy)
            except GPSRejected as exc:
                raise CockpitError(str(exc), 422) from exc
            return _public(world)

    def zoom(self, world_id: str, direction: int) -> dict:
        with self._lock:
            world = self._require(world_id)
            layer = _layer(world, world.camera.layer_id)
            try:
                world.camera = zoom_minimap(world.camera, layer, direction)
            except GPSRejected as exc:
                raise CockpitError(str(exc), 422) from exc
            return _public(world)

    def jump(self, world_id: str, layer_id: str) -> dict:
        with self._lock:
            world = self._require(world_id)
            source = _layer(world, world.camera.layer_id)
            dest = _layer(world, layer_id)
            try:
                world.camera = jump_minimap_layer(world.camera, source, dest)
            except GPSRejected as exc:
                raise CockpitError(str(exc), 422) from exc
            return _public(world)

    def portal(self, world_id: str, portal_id: str) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                world.camera = follow_portal(world.camera, world.layers, world.portals, portal_id)
            except GPSRejected as exc:
                raise CockpitError(str(exc), 422) from exc
            return _public(world)

    def save_baseline(self, world_id: str, body: dict) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                stations = {
                    item["control_id"]: ControlStation(item["control_id"], item["x"], item["y"], item["z"])
                    for item in body["stations"]
                }
                baseline = BaselineRecord(
                    body["baseline_id"], FICTIONAL_DATUM, body["epoch"], body["instrument"],
                    body["surveyor"], body.get("notes") or "", stations,
                )
                world.survey.put_baseline(baseline)
            except (KeyError, TypeError, SurveyAuthorityError) as exc:
                raise CockpitError(str(exc) or "baseline draft is invalid", 422) from exc
            return _public(world)

    def approve_baseline(self, world_id: str, baseline_id: str, actor: str) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                world.survey.approve_baseline(baseline_id, actor)
            except SurveyAuthorityError as exc:
                raise CockpitError(str(exc)) from exc
            return _public(world)

    def save_sighting(self, world_id: str, body: dict) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                world.survey.put_sighting(SightingRecord(
                    body["sighting_id"], body["baseline_id"], body["control_id"],
                    body["bearing_deg"], body["distance_m"], body["uncertainty_m"],
                ))
            except (KeyError, TypeError, SurveyAuthorityError) as exc:
                raise CockpitError(str(exc) or "sighting draft is invalid", 422) from exc
            return _public(world)

    def approve_sighting(self, world_id: str, sighting_id: str, actor: str) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                world.survey.approve_sighting(sighting_id, actor)
            except SurveyAuthorityError as exc:
                raise CockpitError(str(exc)) from exc
            return _public(world)

    def solve(self, world_id: str, sighting_ids: list[str], actor: str) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                fix = world.survey.solve(sighting_ids, entity_id="avatar")
            except SurveyAuthorityError as exc:
                raise CockpitError(str(exc)) from exc
            payload = {
                "entity_id": fix.entity_id,
                "x": fix.x,
                "y": fix.y,
                "z": fix.z,
                "region": fix.region,
                "datum": FICTIONAL_DATUM,
                "approved_by_fix": actor,
                "consumed_ids": list(sighting_ids),
                "measured_earth_position": False,
            }
            world.last_fix = payload
            world.fixes.append(payload)
            del world.fixes[:-16]
            return _public(world)

    def propose(self, world_id: str, body: dict, actor: str, now_ms: int) -> dict:
        with self._lock:
            world = self._require(world_id)
            before = world.ledger.canon_digest()
            revision = world.ledger.state.revision
            try:
                page = _page_from_body(body)
                world.ledger.propose(
                    page,
                    current={body["signal"]: body["current_value"]},
                    actor=actor,
                    now_ms=now_ms,
                )
            except (KeyError, TypeError, RPGEventError, EventAuthorityError) as exc:
                raise CockpitError(str(exc) or "event could not be proposed", 422) from exc
            if world.ledger.canon_digest() != before or world.ledger.state.revision != revision:
                raise CockpitError("proposal mutated quest canon")
            return _public(world)

    def authorize_operator(self, world_id: str, actor: str) -> None:
        """Record an operator the commit route has already admitted."""
        who = actor.strip()
        if not who or who.lower() == "anonymous":
            raise CockpitError("actor identity required", 422)
        with self._lock:
            world = self._require(world_id)
            world.ledger.keys[who] = SERVER_KEY

    def commit(self, world_id: str, proposal_id: str, expected: str, actor: str, now_ms: int) -> dict:
        with self._lock:
            world = self._require(world_id)
            try:
                world.ledger.commit(
                    proposal_id, actor=actor, expected_canon_digest=expected, now_ms=now_ms,
                )
            except EventAuthorityError as exc:
                raise CockpitError(str(exc)) from exc
            return _public(world)

    def _require(self, world_id: str) -> CockpitWorld:
        if world_id == DEMO_WORLD and world_id not in self._worlds:
            self._worlds[world_id] = _demo_world()
        world = self._worlds.get(world_id)
        if world is None:
            raise CockpitError("unknown fictional world", 404)
        return world


def _layer(world: CockpitWorld, layer_id: str) -> FictionalMapLayer:
    found = next((layer for layer in world.layers if layer.layer_id == layer_id), None)
    if found is None:
        raise CockpitError("unknown fictional layer", 404)
    return found


def _page_from_body(body: dict) -> RPGEventPage:
    preset = body.get("preset")
    if preset == "start-lantern":
        return RPGEventPage(
            "meadow-rain-lantern", 5,
            (EnvironmentalTrigger("rain_mm_h", "above", 1.0),),
            (RPGEventAction("start_quest", "quest", "lantern-watch", ""),),
            cooldown_ms=60_000,
        )
    if preset == "advance-lantern":
        return RPGEventPage(
            "meadow-rain-shelter", 5,
            (EnvironmentalTrigger("rain_mm_h", "above", 1.0),),
            (RPGEventAction("advance_quest", "quest", "lantern-watch", "sheltered"),),
            cooldown_ms=60_000,
        )
    return RPGEventPage(
        body["page_id"], int(body["priority"]),
        (EnvironmentalTrigger(body["signal"], body["comparison"], float(body["threshold"])),),
        (RPGEventAction(body["action_kind"], body["action_channel"], body["action_target"], body.get("action_value") or ""),),
        cooldown_ms=int(body.get("cooldown_ms") or 0),
    )


def _demo_world() -> CockpitWorld:
    layers = (
        FictionalMapLayer("crypt", "underground", 24, 24, -18),
        FictionalMapLayer("meadow", "surface", 32, 32, 12),
        FictionalMapLayer("aether-isle", "sky-island", 16, 16, 240),
    )
    portals = validate_fictional_portals(layers, (
        FictionalPortal("well", "meadow", 8, 8, "crypt", 4, 4, True),
        FictionalPortal("spire", "meadow", 20, 6, "aether-isle", 3, 3, True),
    ))
    survey = SurveyBook()
    survey.put_baseline(BaselineRecord(
        "meadow-baseline", FICTIONAL_DATUM, "Third Lantern Era",
        "fictional bubble sextant", "Mara Quill",
        "Stations are authored metres in the meadow realm, not surveyed Earth coordinates.",
        {
            "station-oak": ControlStation("station-oak", 0, 0, 12),
            "station-cairn": ControlStation("station-cairn", 10, 10, 12),
        },
    ))
    survey.put_sighting(SightingRecord("sight-oak", "meadow-baseline", "station-oak", 90, 10, 0.4))
    survey.put_sighting(SightingRecord("sight-cairn", "meadow-baseline", "station-cairn", 180, 10, 0.4))
    ledger = EnvironmentalLedger(
        SaveState("meadow"),
        CanonRules.build((
            QuestSpec("lantern-watch", ("notice", "sheltered"), era_engines=frozenset({"meadow"})),
        )),
    )
    ledger.propose(
        _page_from_body({"preset": "start-lantern"}),
        current={"rain_mm_h": 4.0},
        actor="meadow-keeper",
        now_ms=10_000,
    )
    if ledger.state.revision != 0 or ledger.state.quest_stage:
        raise RuntimeError("demo proposal must not mutate the save")
    return CockpitWorld(DEMO_WORLD, layers, portals, opening_camera(layers), survey, ledger)


def _public(world: CockpitWorld) -> dict:
    layer = next(item for item in world.layers if item.layer_id == world.camera.layer_id)
    view = minimap_viewport(world.camera, layer)
    zoom_index = MINIMAP_ZOOMS.index(world.camera.zoom)
    here = world.camera.layer_id
    exits = []
    for portal in world.portals:
        if portal.source_layer == here:
            exits.append(_portal_public(portal, portal.dest_layer, portal.dest_x, portal.dest_y))
        elif portal.bidirectional and portal.dest_layer == here:
            exits.append(_portal_public(portal, portal.source_layer, portal.source_x, portal.source_y))
    baseline = next(iter(world.survey.baselines.values()), None)
    return {
        "schema": "skeleton.frontier.cockpit.v1",
        "world_id": world.world_id,
        "fictional_only": True,
        "datum": FICTIONAL_DATUM,
        "device_geolocation": False,
        "layer_kinds": list(FICTIONAL_LAYER_KINDS),
        "map": {
            "layers": [
                {
                    "layer_id": item.layer_id, "kind": item.kind,
                    "width": item.width, "height": item.height,
                    "elevation_m": item.elevation_m,
                }
                for item in world.layers
            ],
            "portals": [
                {
                    "portal_id": portal.portal_id,
                    "source_layer": portal.source_layer,
                    "source_x": portal.source_x, "source_y": portal.source_y,
                    "dest_layer": portal.dest_layer,
                    "dest_x": portal.dest_x, "dest_y": portal.dest_y,
                    "bidirectional": portal.bidirectional,
                }
                for portal in world.portals
            ],
            "exits": exits,
            "camera": {
                "layer_id": world.camera.layer_id,
                "zoom": world.camera.zoom,
                "center_x": world.camera.center_x,
                "center_y": world.camera.center_y,
            },
            "viewport": view,
            "zoom_levels": list(MINIMAP_ZOOMS),
            "can_zoom_in": zoom_index < len(MINIMAP_ZOOMS) - 1,
            "can_zoom_out": zoom_index > 0,
        },
        "baseline": None if baseline is None else {
            "baseline_id": baseline.baseline_id,
            "datum": baseline.datum,
            "epoch": baseline.epoch,
            "instrument": baseline.instrument,
            "surveyor": baseline.surveyor,
            "notes": baseline.notes,
            "status": baseline.status,
            "approved_by": baseline.approved_by,
            "stations": [
                {"control_id": station.control_id, "x": station.x, "y": station.y, "z": station.z}
                for station in baseline.stations.values()
            ],
        },
        "sightings": [
            {
                "sighting_id": item.sighting_id,
                "baseline_id": item.baseline_id,
                "control_id": item.control_id,
                "bearing_deg": item.bearing_deg,
                "distance_m": item.distance_m,
                "uncertainty_m": item.uncertainty_m,
                "state": item.state,
                "approved_by": item.approved_by,
            }
            for item in world.survey.sightings.values()
        ],
        "fix": world.last_fix,
        "events": {
            "canon_digest": world.ledger.canon_digest(),
            "era_engine": world.ledger.state.era_engine,
            "revision": world.ledger.state.revision,
            "quest_stage": dict(world.ledger.state.quest_stage),
            "quests": [
                {"quest_id": quest.quest_id, "stages": list(quest.stages)}
                for quest in world.ledger.canon.quests.values()
            ],
            "completed_quests": sorted(world.ledger.state.completed_quests),
            "proposals": [
                {
                    "proposal_id": item.proposal_id,
                    "page_id": item.page_id,
                    "priority": item.priority,
                    "cooldown_ms": item.cooldown_ms,
                    "canon_digest": item.canon_digest,
                    "proposed_by": item.proposed_by,
                    "status": world.ledger.status(item.proposal_id),
                    "mutated": world.ledger.status(item.proposal_id) == "committed",
                    "actions": [
                        {"kind": action.kind, "channel": action.channel,
                         "target": action.target, "value": action.value}
                        for action in item.decision.actions
                    ],
                }
                for item in world.ledger.proposals()
            ],
        },
    }


def _portal_public(portal: FictionalPortal, layer: str, x: int, y: int) -> dict:
    return {
        "portal_id": portal.portal_id,
        "label": portal.portal_id,
        "dest_layer": layer,
        "dest_x": x,
        "dest_y": y,
    }


_SERVICE: FrontierCockpitService | None = None


def get_service() -> FrontierCockpitService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = FrontierCockpitService()
    return _SERVICE


def reset_service() -> FrontierCockpitService:
    global _SERVICE
    _SERVICE = FrontierCockpitService()
    return _SERVICE
