"""Modern RPG creation tools over canonical era-game/Forge owners.

Declarative, portable, no generated executable scripts: multi-layer 2D/3D
map editing, prefabs, actors, class skills, quest flags, dialogue events,
cutscenes, world weather, lighting, fluid, audio and editor operations.
The runtime returns proposals for canonical Godot/engine confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from hashlib import sha256
import json

from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from skeleton.jeeves.game_frontier_production import ERA_TRIANGLE_BUDGETS
from skeleton.forge.game_frontier_rpg_events import RPGEventPage, event_authoring_catalog
from skeleton.jeeves.game_frontier_virtual_navigation import GameMap, VirtualNavigationRequest, compose_virtual_navigation


class StudioError(ValueError):
    pass


STUDIO_TOOLS = (
    "tile_brush", "terrain_sculpt", "voxel_model", "mesh_editor",
    "material_painter", "sprite_animator", "skeletal_rigger",
    "character_creator", "dialogue_graph", "quest_graph",
    "cinematic_timeline", "event_pages", "battle_designer",
    "party_editor", "class_editor", "inventory_editor", "economy_editor",
    "world_axis_editor", "world_portals", "weather_lab", "water_simulator",
    "solar_lunar_tides", "soundscape_mixer", "ray_light_editor",
    "shadow_coherence", "prefab_catalog", "procedural_chunker",
    "dual_verifier", "console_era_compiler", "live_playtest",
    "environmental_trigger_graph", "weather_condition_event_pages",
    "instrument_event_graph", "elastic_body_skin3d_editor",
    "limb_weight_painter", "center_of_mass_inspector",
    "stability_polygon_inspector", "impact_material_composer",
    "gyro_simulator", "magnetic_compass_calibrator",
    "sextant_navigation_table", "bubble_sextant_lab",
    "barometric_altimeter_calibration", "trig_altimeter_survey",
    "quest_branch_verifier", "npc_perception_map",
    "cinematic_environment_sync", "terrain_traction_authoring",
    "physics_receipt_viewer", "rpg_event_conflict_resolver",
    "virtual_world_gps_map", "fictional_beacon_constellation",
    "world_landmark_survey", "gps_resection_debugger",
    "map_route_waypoints", "realm_coordinate_viewer",
    "frame_location_coherence", "gdd_navigation_context",
    "native_3d_trigger_volume_editor", "authored_quest_zone_bindings",
    "native_zone_event_timeline_inspector",
    "native_runtime_rpg_event_compiler", "native_physics_sensor_bindings",
    "native_3d_airflow_field_editor", "native_rigid_body_field_receipt_inspector",
    "native_quest_graph_compiler", "native_quest_stage_branch_editor",
    "native_approved_session_replay_inspector",
    "authored_tile_operations", "authored_prefab_and_actor_operations",
    "authored_quest_event_music_operations", "authored_transactional_editor",
    "authored_playable_godot_export",
)


@dataclass(frozen=True)
class StudioEvent:
    event_id: str
    trigger: str
    condition_flag: str
    condition_value: bool
    action: str
    target: str
    value: str

    def __post_init__(self):
        for value in (self.event_id,self.condition_flag,self.target,self.value):
            if type(value) is not str or len(value)>128:
                raise StudioError("bounded event fields required")
        if self.trigger not in ("interact","enter","exit","timer","weather","tide","quest","collision"):
            raise StudioError("unsupported event trigger")
        if self.action not in ("set_flag","show_dialogue","play_audio","open_portal",
                               "start_quest","grant_item","set_weather",
                               "change_camera","play_cutscene","spawn_prefab"):
            raise StudioError("action not available")
        if type(self.condition_value) is not bool:
            raise StudioError("typed condition required")


@dataclass(frozen=True)
class StudioPrefab:
    prefab_id: str
    kind: str
    era: str
    asset_digest: str
    interaction_type: str = "none"

    def __post_init__(self):
        if not self.prefab_id or len(self.prefab_id)>128:
            raise StudioError("prefab identity required")
        if self.kind not in ("npc","character","building","prop","foliage",
                             "liquid","terrain","portal","particle","audio"):
            raise StudioError("unsupported prefab")
        if self.era not in ERA_TRIANGLE_BUDGETS and self.era not in ("sprite","tile"):
            raise StudioError("unknown render era")
        if len(self.asset_digest)!=64 or any(x not in "0123456789abcdef" for x in self.asset_digest):
            raise StudioError("prefab content digest required")
        if self.interaction_type not in ("none","dialogue","pickup","collision","door","combat","craft"):
            raise StudioError("invalid interaction")


@dataclass(frozen=True)
class MapLayer:
    layer_id: str
    width: int
    height: int
    palette: tuple[str,...]
    data: tuple[int,...]
    elevation_m: float = 0

    def __post_init__(self):
        if not self.layer_id or len(self.layer_id)>128:
            raise StudioError("layer id required")
        if type(self.width) is not int or type(self.height) is not int or not (1<=self.width<=256 and 1<=self.height<=256):
            raise StudioError("layer dimensions must be 1..256")
        if len(self.data)!=self.width*self.height or not (1<=len(self.palette)<=256):
            raise StudioError("map content dimensions/palette invalid")
        if any(type(x) is not int or not -1<=x<len(self.palette) for x in self.data):
            raise StudioError("map palette reference invalid")
        if type(self.elevation_m) not in (int,float) or not -1e5<=self.elevation_m<=1e5:
            raise StudioError("invalid elevation")


def paint_tile(layer: MapLayer, *, x: int, y: int, tile_index: int) -> MapLayer:
    from dataclasses import replace
    if (type(x) is not int or type(y) is not int or
            not 0<=x<layer.width or not 0<=y<layer.height or
            type(tile_index) is not int or not -1<=tile_index<len(layer.palette)):
        raise StudioError("tile paint bounds invalid")
    new=list(layer.data)
    new[y*layer.width+x]=tile_index
    return replace(layer,data=tuple(new))


@dataclass(frozen=True)
class StudioPlacement:
    prefab_id: str
    x: float
    y: float
    z: float
    facing_deg: float = 0.

    def __post_init__(self):
        import math
        if not self.prefab_id or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e7
                                     for v in (self.x,self.y,self.z,self.facing_deg)):
            raise StudioError("invalid placement")


@dataclass(frozen=True)
class StudioTriggerVolume:
    """Studio-owned 3D zone bound to a placed actor and existing RPG event."""
    zone_id: str
    actor_entity_id: str
    event_page_id: str
    radius_m: float
    offset_xyz_m: tuple[float,float,float] = (0.,0.,0.)

    def __post_init__(self):
        import math
        from skeleton.jeeves.game_frontier_native_zones import _ID
        for name in (self.zone_id,self.actor_entity_id,self.event_page_id):
            if type(name) is not str or not _ID.fullmatch(name):
                raise StudioError("bounded studio zone/actor/event identity required")
        if (type(self.radius_m) not in (float,int) or
            not math.isfinite(self.radius_m) or not .1<=self.radius_m<=10000):
            raise StudioError("authored zone radius outside native game engine bounds")
        if (not isinstance(self.offset_xyz_m,tuple) or len(self.offset_xyz_m)!=3 or
            any(type(v) not in (float,int) or not math.isfinite(v) or abs(v)>10000
                for v in self.offset_xyz_m)):
            raise StudioError("finite 3D zone-relative source offset required")


@dataclass(frozen=True)
class StudioForceField:
    """Authored, physically active 3D field anchored to an existing placement."""
    field_id: str
    actor_entity_id: str
    kind: str
    radius_m: float
    acceleration_mps2: float
    center_offset_xyz_m: tuple[float,float,float] = (0.,0.,0.)

    def __post_init__(self):
        from skeleton.jeeves.game_frontier_native_fields import (
            normalize_native_force_fields,NativeForceFieldError,
        )
        try:
            normalize_native_force_fields(({
                "id":self.field_id,"actor_id":self.actor_entity_id,
                "kind":self.kind,"radius_m":self.radius_m,
                "acceleration_mps2":self.acceleration_mps2,
                "center_xyz_m":self.center_offset_xyz_m,
            },))
        except NativeForceFieldError as exc:
            raise StudioError("invalid Studio field type, mass force or coordinate bounds") from exc



_STUDIO_QUEST_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class StudioQuestStage:
    stage_id: str
    objective: str
    next_stage_ids: tuple[str,...] = ()

    def __post_init__(self):
        if (type(self.stage_id) is not str or
            _STUDIO_QUEST_ID.fullmatch(self.stage_id) is None or
            type(self.objective) is not str or
            not 1<=len(self.objective)<=512 or
            type(self.next_stage_ids) is not tuple or
            len(self.next_stage_ids)>32 or
            any(type(s) is not str or _STUDIO_QUEST_ID.fullmatch(s) is None
                for s in self.next_stage_ids)):
            raise StudioError("bounded typed native quest stage required")


@dataclass(frozen=True)
class StudioQuest:
    quest_id: str
    title: str
    first_stage_id: str
    stages: tuple[StudioQuestStage,...]

    def __post_init__(self):
        if (type(self.quest_id) is not str or
            _STUDIO_QUEST_ID.fullmatch(self.quest_id) is None or
            type(self.first_stage_id) is not str or
            _STUDIO_QUEST_ID.fullmatch(self.first_stage_id) is None or
            type(self.title) is not str or not 1<=len(self.title)<=256 or
            type(self.stages) is not tuple or not 1<=len(self.stages)<=4096 or
            any(not isinstance(s,StudioQuestStage) for s in self.stages)):
            raise StudioError("bounded authored quest graph required")

@dataclass(frozen=True)
class StudioProject:
    project_id: str
    target_era: str
    projection: ProjectionMode
    world_family: WorldFamily
    layers: tuple[MapLayer,...]
    prefabs: tuple[StudioPrefab,...] = ()
    placements: tuple[StudioPlacement,...] = ()
    events: tuple[StudioEvent,...] = ()
    soundtrack_ids: tuple[str,...] = ()
    environmental_pages: tuple[RPGEventPage, ...] = ()
    virtual_game_map: GameMap | None = None
    native_trigger_volumes: tuple[StudioTriggerVolume,...] = ()
    native_gameplay_force_fields: tuple[StudioForceField,...] = ()
    native_quests: tuple[StudioQuest,...] = ()

    def __post_init__(self):
        if not self.project_id or len(self.project_id)>128:
            raise StudioError("project id required")
        if self.target_era not in ERA_TRIANGLE_BUDGETS and self.target_era not in ("sprite","tile"):
            raise StudioError("target era required")
        if not isinstance(self.projection,ProjectionMode) or not isinstance(self.world_family,WorldFamily):
            raise StudioError("valid world and projection required")
        if not 1<=len(self.layers)<=128 or len(self.prefabs)>4096 or len(self.placements)>100000 or len(self.events)>8192 or len(self.environmental_pages)>4096:
            raise StudioError("authoring budgets exceeded")
        ids=[l.layer_id for l in self.layers]
        if len(set(ids))!=len(ids):
            raise StudioError("duplicate map layer")
        if self.virtual_game_map is not None and (
            self.virtual_game_map.world_id != self.project_id or
            self.virtual_game_map.realm_id != self.world_family.value
        ):
            raise StudioError("virtual map must match authored project and realm")
        pids=[p.prefab_id for p in self.prefabs]
        if len(set(pids))!=len(pids):
            raise StudioError("duplicate prefab")
        if any(p.prefab_id not in pids for p in self.placements):
            raise StudioError("placement must resolve existing prefab")
        events=[x.event_id for x in self.events]
        if len(set(events))!=len(events):
            raise StudioError("duplicate event id")
        if type(self.native_trigger_volumes) is not tuple or (
            len(self.native_trigger_volumes)>64 or
            any(not isinstance(zone,StudioTriggerVolume)
                for zone in self.native_trigger_volumes)):
            raise StudioError("at most 64 typed native game zones")
        if (type(self.native_gameplay_force_fields) is not tuple or
            len(self.native_gameplay_force_fields)>64 or
            any(not isinstance(field,StudioForceField)
                for field in self.native_gameplay_force_fields)):
            raise StudioError("bounded typed gameplay force field catalog required")
        if (type(self.native_quests) is not tuple or len(self.native_quests)>128 or
            any(not isinstance(q,StudioQuest) for q in self.native_quests)):
            raise StudioError("bounded Studio quest catalog required")
        if self.native_quests:
            from skeleton.jeeves.game_frontier_native_quest_session import (
                NativeQuestSessionError, parse_native_quest_graph,
            )
            try:
                parse_native_quest_graph(_studio_quest_source(self.native_quests))
            except NativeQuestSessionError as exc:
                raise StudioError("Studio quest branches must be complete and reachable") from exc
        field_ids=[field.field_id for field in self.native_gameplay_force_fields]
        if len(field_ids)!=len(set(field_ids)):
            raise StudioError("duplicate Studio gameplay force field")
        zones=[z.zone_id for z in self.native_trigger_volumes]
        if len(set(zones))!=len(zones):
            raise StudioError("duplicate authored gameplay zone")
        actor_sources={
            placement.prefab_id+":"+str(index):placement.prefab_id
            for index,placement in enumerate(self.placements)}
        if any(field.actor_entity_id not in actor_sources
               for field in self.native_gameplay_force_fields):
            raise StudioError("gameplay force field actor has no placed source prefab")
        authored_events={e.event_id:e for e in self.events}
        for zone in self.native_trigger_volumes:
            event=authored_events.get(zone.event_page_id)
            actor_prefab=actor_sources.get(zone.actor_entity_id)
            if actor_prefab is None or event is None or (
                event.trigger!="enter" or
                event.target not in (zone.actor_entity_id,actor_prefab) or
                event.condition_flag or
                event.action not in ("show_dialogue","start_quest","play_audio")):
                raise StudioError("gameplay volume must bind a placed actor and executable-preview-safe event")
        page_ids=[page.page_id for page in self.environmental_pages]
        if len(page_ids)!=len(set(page_ids)) or set(page_ids).intersection(events):
            raise StudioError("duplicate or colliding environmental page id")

    def authored_manifest(self) -> dict:
        return {
            "schema":"skeleton.forge.frontier_studio.v1",
            "project_id":self.project_id,"target_era":self.target_era,
            "projection":self.projection.value,"world_family":self.world_family.value,
            "editors":STUDIO_TOOLS,
            "layers":[{"id":l.layer_id,"w":l.width,"h":l.height,
                       "palette":l.palette,"data":l.data,"elevation":l.elevation_m}
                      for l in self.layers],
            "prefabs":[p.__dict__ for p in self.prefabs],
            "placements":[p.__dict__ for p in self.placements],
            "events":[e.__dict__ for e in self.events],
            "environmental_pages":[{
                "id":page.page_id,"priority":page.priority,
                "conditions":[condition.__dict__ for condition in page.conditions],
                "actions":[action.__dict__ for action in page.actions],
                "flags":page.required_flags,
                "cooldown_ms":page.cooldown_ms,
                "enabled":page.enabled,"repeat":page.repeat,
            } for page in self.environmental_pages],
            "environmental_editor_catalog":event_authoring_catalog(),
            "native_trigger_volumes":[{
                "zone_id":zone.zone_id,"actor_entity_id":zone.actor_entity_id,
                "event_page_id":zone.event_page_id,"radius_m":zone.radius_m,
                "offset_xyz_m":list(zone.offset_xyz_m),
            } for zone in self.native_trigger_volumes],
            "native_gameplay_force_fields":[{
                "id":field.field_id,"actor_id":field.actor_entity_id,
                "kind":field.kind,"radius_m":field.radius_m,
                "acceleration_mps2":field.acceleration_mps2,
                "offset_xyz_m":list(field.center_offset_xyz_m),
            } for field in self.native_gameplay_force_fields],
            "native_quests":_studio_quest_source(self.native_quests)["quests"],
            "soundtrack":self.soundtrack_ids,
            "virtual_game_map": ({
                "world_id":self.virtual_game_map.world_id,
                "realm_id":self.virtual_game_map.realm_id,
                "map_digest":self.virtual_game_map.identity(),
                "width_tiles":self.virtual_game_map.width_tiles,
                "height_tiles":self.virtual_game_map.height_tiles,
                "tile_size_m":self.virtual_game_map.tile_size_m,
            } if self.virtual_game_map is not None else None),
            "authority":"candidate_not_executed",
        }


def compile_studio_project(project: StudioProject) -> dict:
    """Produce deterministic editor→engine candidate with hash provenance."""
    m=project.authored_manifest()
    canonical=json.dumps(m,sort_keys=True,separators=(",",":"),allow_nan=False)
    m["content_sha256"]=sha256(canonical.encode()).hexdigest()
    return m


def compile_studio_gameplay_zones(project: StudioProject) -> dict:
    """Compile real placed prefab XYZ and authored event IDs to native zones.

    This tool returns exactly the `native_gameplay_zones` descriptors accepted
    by the existing Godot exporter. Quest/dialogue/audio remain proposals,
    not unauthorized GDD changes or arbitrary script execution.
    """
    from skeleton.jeeves.game_frontier_native_zones import normalize_gameplay_zones
    if not isinstance(project,StudioProject):
        raise StudioError("typed Studio project required for RPG volume export")
    placements={
        placement.prefab_id+":"+str(index):placement
        for index,placement in enumerate(project.placements)}
    events={event.event_id:event for event in project.events}
    source=[]
    for zone in project.native_trigger_volumes:
        placement=placements[zone.actor_entity_id]
        page=events[zone.event_page_id]
        mapping={"show_dialogue":"show_dialogue","start_quest":"start_quest",
                 "play_audio":"spatial_audio"}
        source.append({
            "id":zone.zone_id,"actor_id":zone.actor_entity_id,
            "center_xyz_m":[a+b for a,b in zip(
                (placement.x,placement.y,placement.z),zone.offset_xyz_m)],
            "radius_m":zone.radius_m,"event_page_id":page.event_id,
            "action_kind":mapping[page.action],
        })
    try:
        catalog=normalize_gameplay_zones(
            source,allowed_actors=set(placements))
    except ValueError as exc:
        raise StudioError("studio trigger cannot compile to native game coordinates") from exc
    report={
        "schema":"skeleton.forge.native_gameplay_zone_compilation.v1",
        "project_id":project.project_id,
        "studio_manifest_digest":compile_studio_project(project)["content_sha256"],
        "zones":catalog,
        "zone_count":len(catalog),
        "available_action_preview_only":True,
        "authority":"studio_authored_zone_candidate_no_world_mutation",
    }
    report["receipt_digest"]=sha256(json.dumps(
        report,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return report


def compile_studio_gameplay_force_fields(project: StudioProject) -> dict:
    """Materialize native engine forces around authored placed Studio actors.

    Emit the exact typed `native_gameplay_force_fields` argument accepted
    by the Godot exporter, with a Studio manifest provenance receipt.
    """
    from skeleton.jeeves.game_frontier_native_fields import (
        normalize_native_force_fields,NativeForceFieldError,
    )
    if not isinstance(project,StudioProject):
        raise StudioError("typed source Studio project required")
    placements={
        placement.prefab_id+":"+str(index):placement
        for index,placement in enumerate(project.placements)}
    source=[]
    for field in project.native_gameplay_force_fields:
        location=placements[field.actor_entity_id]
        center=[a+b for a,b in zip(
            (location.x,location.y,location.z),field.center_offset_xyz_m)]
        source.append({
            "id":field.field_id,"actor_id":field.actor_entity_id,
            "kind":field.kind,
            "center_xyz_m":center,"radius_m":field.radius_m,
            "acceleration_mps2":field.acceleration_mps2,
        })
    try:
        normalized=normalize_native_force_fields(
            source,allowed_actors=set(placements))
    except NativeForceFieldError as exc:
        raise StudioError("native runtime field source invalid") from exc
    report={
        "schema":"skeleton.forge.studio_native_fields.v1",
        "project_id":project.project_id,
        "studio_manifest_digest":compile_studio_project(project)["content_sha256"],
        "fields":normalized,"field_count":len(normalized),
        "authority":"source_authored_physics_candidate_no_canon_mutation",
    }
    report["receipt_digest"]=sha256(json.dumps(
        report,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return report



def _studio_quest_source(quests: tuple[StudioQuest,...]) -> dict:
    return {
        "schema":"skeleton.game.native_quest_graph.v1",
        "quests":[{
            "id":q.quest_id,"title":q.title,"start":q.first_stage_id,
            "stages":[{"id":s.stage_id,"objective":s.objective,
                       "next":list(s.next_stage_ids)} for s in q.stages],
        } for q in quests],
    }


def compile_studio_native_quest_graph(project: StudioProject) -> dict:
    """Export source-authored, multi-branch quests to native RPG session replay.

    Quest catalog is bound into the Studio project's authored manifest;
    the gameplay session needs separately reviewed local approvals before any
    quest state advances. No scene or canonical GDD is mutated by compilation.
    """
    from skeleton.jeeves.game_frontier_native_quest_session import (
        parse_native_quest_graph, NativeQuestSessionError,
    )
    if not isinstance(project,StudioProject):
        raise StudioError("typed Studio quest project required")
    try:
        return parse_native_quest_graph(_studio_quest_source(project.native_quests))
    except NativeQuestSessionError as exc:
        raise StudioError("Studio quest graph failed typed source verifier") from exc


def compile_studio_native_rpg_pages(
    project: StudioProject, *,
    actor_entity_id: str,
) -> dict:
    """Export already-authored Studio environmental pages to real native RPG.

    Only source sensors reported by the Godot gameplay journal can be
    compiled. A weather or environmental signal not observed in the selected
    engine run cannot silently become an invented runtime measurement.
    """
    from skeleton.jeeves.game_frontier_native_rpg_bridge import (
        NATIVE_RPG_SIGNALS, parse_native_rpg_pages,
    )
    if not isinstance(project,StudioProject) or type(actor_entity_id) is not str:
        raise StudioError("typed native RPG project and actor required")
    placements={
        p.prefab_id+":"+str(index):p.prefab_id
        for index,p in enumerate(project.placements)}
    prefab=placements.get(actor_entity_id)
    if prefab is None:
        raise StudioError("native RPG actor must be an authored placed source")
    pages=[]
    for page in project.environmental_pages:
        if any(condition.signal not in NATIVE_RPG_SIGNALS
               for condition in page.conditions):
            raise StudioError("Studio environmental page has no observed native physics sensor")
        if any(action.target not in (actor_entity_id,prefab)
               for action in page.actions):
            raise StudioError("native RPG page target is not the selected source actor")
        pages.append({
            "id":page.page_id,"priority":page.priority,
            "conditions":[condition.__dict__ for condition in page.conditions],
            "actions":[action.__dict__ for action in page.actions],
            "required_flags":[{"name":name,"value":value}
                              for name,value in page.required_flags],
            "cooldown_ms":page.cooldown_ms,
            "enabled":page.enabled,"repeat":page.repeat,
        })
    report={
        "schema":"skeleton.game.native_rpg_pages.v1",
        "pages":pages,
        "authored_studio_digest":compile_studio_project(project)["content_sha256"],
        "source_actor_id":actor_entity_id,
        "authority":"Studio_native_RPG_source_proposals_not_world_mutations",
    }
    report["receipt_digest"]=sha256(json.dumps(
        report,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    try:
        parsed=parse_native_rpg_pages(report)
    except ValueError as exc:
        raise StudioError("Studio native RPG pages failed common typed verifier") from exc
    if len(parsed)!=len(project.environmental_pages):
        raise StudioError("Studio native RPG page coverage incomplete")
    return report


def propose_event_actions(project: StudioProject, *, trigger: str,
                          flags: dict[str,bool], actor_target: str) -> tuple[dict,...]:
    """Evaluate declarative conditional event pages; never execute actions."""
    if not isinstance(flags,dict) or any(type(v) is not bool for v in flags.values()):
        raise StudioError("flags require bool values")
    proposal=[]
    for event in project.events:
        if (event.trigger==trigger and event.target==actor_target and
                (not event.condition_flag or flags.get(event.condition_flag,False)==event.condition_value)):
            proposal.append({"event":event.event_id,"action":event.action,
                             "target":event.target,"value":event.value,
                             "authority":"candidate_not_executed"})
    return tuple(proposal)


def compile_studio_frame(
    project: StudioProject,
    signed_gdd: dict,
    *, frame_index: int,
    fps: int,
    preceding_frames: tuple = (),
    notes: tuple = (),
    entity_velocities: dict[str, tuple[float,float,float]] | None = None,
    previous_frame: object | None = None,
    context_cursor: object | None = None,
    previous_chunk_evidence: dict | None = None,
    virtual_navigation: VirtualNavigationRequest | None = None,
    previous_virtual_navigation: dict | None = None,
) -> dict:
    """Build one *verified* Studio progress frame from actual placed prefabs.

    A source-authored and signed GDD is mandatory. Entity IDs and immutable
    content digests come from the existing StudioProject, rather than a second
    GDD or an AI-authored invented state. Live AI input is only the linked
    between-frame note; no mutable gameplay changes occur.
    """
    from skeleton.jeeves.game_frontier_frame_coherence import (
        GDDFrameNote, FrameObject, bind_signed_gdd, advance_frame,
        ai_design_context, verify_frame, FrameCoherenceError,
        FrameReceipt, FrameContextCursor, advance_context_cursor,
        cursor_ai_context,
    )
    from skeleton.jeeves.game_frontier_production import Vec3
    from skeleton.jeeves.game_frontier_chunk_evidence import build_frame_chunk_receipts
    if not isinstance(project, StudioProject):
        raise StudioError("typed Studio project required")
    anchor=bind_signed_gdd(signed_gdd)
    if anchor.project_id!=project.project_id:
        raise StudioError("signed GDD is for a different project")
    if type(preceding_frames) is not tuple or len(preceding_frames)>10000:
        raise StudioError("bounded prior verified frames required")
    use_incremental = context_cursor is not None or previous_frame is not None
    if use_incremental and (
        preceding_frames or not isinstance(previous_frame,FrameReceipt)
        or not isinstance(context_cursor,FrameContextCursor)
    ):
        raise StudioError("efficient frame cursor requires paired prior state")
    if any(not isinstance(n,GDDFrameNote) for n in notes):
        raise StudioError("notes must reference signed GDD world laws")
    by_id={p.prefab_id:p for p in project.prefabs}
    velocities=entity_velocities or {}
    if type(velocities) is not dict or len(velocities)>100000:
        raise StudioError("bounded entity velocities required")
    objects=[]
    for index,placement in enumerate(project.placements):
        prefab=by_id[placement.prefab_id]
        entity_id=placement.prefab_id+":"+str(index)
        speed=velocities.get(entity_id,(0.,0.,0.))
        if type(speed) is not tuple or len(speed)!=3:
            raise StudioError("bounded 3D velocity tuple required")
        objects.append(FrameObject(
            entity_id,Vec3(placement.x,placement.y,placement.z),
            Vec3(*speed),prefab.asset_digest,
        ))
    if not objects:
        raise StudioError("per-frame coherence requires placed source prefabs")
    prior=(previous_frame if use_incremental else
           preceding_frames[-1] if preceding_frames else None)
    if (frame_index != (previous_frame.frame_index+1 if use_incremental
                        else len(preceding_frames))):
        raise StudioError("missing/hole in frame sequence")
    frame=advance_frame(
        frame_index=frame_index,fps=fps,gdd=anchor,
        objects=tuple(objects),previous=prior,notes=tuple(notes),
    )
    chunk_evidence=build_frame_chunk_receipts(
        frame,anchor,previous=prior,previous_evidence=previous_chunk_evidence)
    if previous_virtual_navigation is not None and virtual_navigation is None:
        raise StudioError("prior GPS receipt requires a current virtual map observation")
    if virtual_navigation is not None:
        if (project.virtual_game_map is None or
            project.virtual_game_map.identity() != virtual_navigation.world.identity()):
            raise StudioError("virtual navigation must use authored RPG game map")
    game_nav = (compose_virtual_navigation(
        virtual_navigation,frame=frame,gdd=anchor,previous_frame=prior,
        previous_navigation=previous_virtual_navigation)
        if virtual_navigation is not None else None)
    latest_cursor=advance_context_cursor(
        anchor,frame,previous_frame=prior,
        previous_cursor=context_cursor if use_incremental else None,
    ) if use_incremental or prior is None else None
    context=(cursor_ai_context(latest_cursor,anchor) if latest_cursor
             else ai_design_context(anchor,(*preceding_frames,frame)))
    # AI receives *verified virtual game-map context*, never OS GPS or
    # an invented GDD rule. Notes remain suggestions for human review.
    if game_nav is not None:
        context = dict(context)
        context["verified_virtual_navigation"] = {
            "world_id": game_nav["world_id"],
            "realm_id": game_nav["realm_id"],
            "map_tile_xy": game_nav["map_tile_xy"],
            "position_xyz_m": game_nav["world_xyz_m"],
            "range_uncertainty_m": game_nav["horizontal_uncertainty_m"],
            "navigation_receipt_digest": game_nav["receipt_digest"],
            "frame_receipt_digest": frame.receipt_digest,
            "source_world_laws_digest": anchor.source_digest,
            "requires_human_canon_approval": True,
            "authority": "AI_design_context_only_virtual_coordinates",
        }
    context=dict(context)
    context["frame_chunk_evidence_digest"]=chunk_evidence["receipt_digest"]
    context["chunk_evidence_source_gdd"]=anchor.source_digest
    base=compile_studio_project(project)
    return {
        "schema":"skeleton.forge.studio_frame_candidate.v1",
        "project":project.project_id,
        "studio_manifest_digest":base["content_sha256"],
        "source_gdd_digest":anchor.source_digest,
        "frame":frame.frame_index,
        "frame_clock_ns":frame.time_ns,
        "chunk_count":len(frame.chunks),
        "chunks":[{"cell":list(c.chunk_key),
                   "content_digest":c.content_digest,
                   "entities":[o.entity_id for o in c.objects]}
                  for c in frame.chunks],
        "verified_a":frame.verifier_a_integrity,
        "verified_b":frame.verifier_b_coherence,
        "frame_receipt_digest":frame.receipt_digest,
        "frame_chunk_evidence":chunk_evidence,
        "chunk_evidence_digest":chunk_evidence["receipt_digest"],
        "note_count":len(frame.note_from_previous),
        "gdd_ai_context":context,
        "virtual_game_gps":game_nav,
        "record":frame,
        "context_cursor":latest_cursor,
        "authority":"studio_preview_proposed_not_engine_mutated",
    }



def author_studio_expedition(project: StudioProject, profile, *, weather=None):
    """Build a playable vertical realm with actual Forge prefab landmarks.

    Seeded sky/cave/underwater traversal is enriched by explicitly authored
    Studio placements. Each accepted placement becomes an interactable waypoint
    linked to its nearest original world node, not a decorative plan entry.
    The typed result runs under the real ExpeditionEpisode state machine.
    """
    from skeleton.jeeves.game_frontier_expedition import (
        ExpeditionError, ExpeditionWorld, TravelEdge, Waypoint,
    )
    from skeleton.jeeves.game_frontier_expedition_generation import (
        ArchipelagoProfile, author_archipelago,
    )
    if not isinstance(project, StudioProject) or not isinstance(profile, ArchipelagoProfile):
        raise StudioError("actual typed Studio project and expedition profile required")
    if project.projection not in {
        ProjectionMode.FULL_3D, ProjectionMode.DEPTH_25,
        ProjectionMode.DEPTH_26, ProjectionMode.DEPTH_27,
        ProjectionMode.DEPTH_28, ProjectionMode.DEPTH_29,
    }:
        raise StudioError("vertical expedition requires 3D or 2.5D-2.9D authored projection")
    if len(project.placements) > 512:
        raise StudioError("expedition placement compilation budget exceeded")
    anchor=compile_studio_project(project)["content_sha256"]
    world=author_archipelago(project.project_id,anchor,profile,weather=weather)
    waypoints=list(world.waypoints)
    edges=list(world.edges)
    originals=tuple(world.waypoints)
    by_prefab={prefab.prefab_id:prefab for prefab in project.prefabs}
    try:
        for index,placement in enumerate(project.placements):
            prefab=by_prefab[placement.prefab_id]
            landmark=f"asset_{index:04d}"
            kind={
                "portal":"ruins","npc":"settlement","character":"settlement",
                "building":"settlement","terrain":"ground","liquid":"underwater",
                "foliage":"canopy",
            }.get(prefab.kind,"ground")
            node=Waypoint(
                landmark,placement.x,placement.y,placement.z,kind,
                landmark=f"Studio original {prefab.prefab_id}",
                safe_rest=prefab.kind in {"building","npc"},
                collectible=f"artifact_{index:04d}" if prefab.interaction_type=="pickup" else "",
                quest_flag=f"visited_{index:04d}" if prefab.interaction_type!="none" else "",
            )
            nearest=min(
                originals,
                key=lambda item:
                (item.x_m-placement.x)**2+(item.y_m-placement.y)**2
                +(item.altitude_m-placement.z)**2,
            )
            distance=(
                (nearest.x_m-placement.x)**2+(nearest.y_m-placement.y)**2
                +(nearest.altitude_m-placement.z)**2
            )**.5
            waypoints.append(node)
            edges.append(TravelEdge(
                f"studio_access_{index:04d}",nearest.waypoint_id,
                landmark,"rope_bridge",max(.01,distance),
                max(1.,distance/3.),2,0.01,30,one_way=False,
            ))
        return ExpeditionWorld(
            project.project_id,anchor,tuple(waypoints),tuple(edges),
            world.arrival,world.destinations,world.weather,
        )
    except ExpeditionError as exc:
        raise StudioError("authored Studio waypoint cannot enter playable expedition") from exc


def compile_studio_expedition(project: StudioProject, profile, *, weather=None,
                              playtest_routes: int = 4,
                              include_godot: bool = True) -> dict:
    """Compile, route-playtest and export a real Studio-derived game realm."""
    from skeleton.jeeves.game_frontier_expedition import world_export
    from skeleton.jeeves.game_frontier_expedition_generation import (
        playtest_archipelago,
    )
    if type(playtest_routes) is not int or not 1<=playtest_routes<=16:
        raise StudioError("playtest route budget must be bounded")
    if type(include_godot) is not bool:
        raise StudioError("Godot game export policy must be explicit")
    world=author_studio_expedition(project,profile,weather=weather)
    report=playtest_archipelago(world,max_routes=playtest_routes)
    compiled=world_export(world)
    assets=[
        {
            "waypoint":f"asset_{index:04d}",
            "prefab_id":placement.prefab_id,
            "asset_digest":next(p.asset_digest for p in project.prefabs
                                if p.prefab_id==placement.prefab_id),
            "source_xyz_m":[placement.x,placement.y,placement.z],
        }
        for index,placement in enumerate(project.placements)
    ]
    out={
        "schema":"skeleton.forge.frontier_studio_expedition.v1",
        "project_id":project.project_id,
        "studio_source_digest":world.source_digest,
        "world_digest":world.digest,
        "waypoints":len(world.waypoints),
        "travel_edges":len(world.by_edge),
        "playtest":report,
        "asset_bindings":assets,
        "engine_candidate":compiled,
        "native_playtest_completed":False,
        "authority":"playable_deterministic_preview_not_native_engine_authority",
    }
    if include_godot:
        from skeleton.jeeves.game_frontier_expedition import Traveler
        from skeleton.jeeves.game_frontier_expedition_godot import (
            emit_expedition_godot_project, verify_expedition_godot_project,
        )
        native_player=Traveler(
            permitted_modes=frozenset((
                "walk","rope_bridge","updraft","glide","airship",
                "portal","climb","dive","swim",
            )),
            flags=frozenset((
                "glider","airship_license","diving_gear","portal_key",
            )),
            equipment=frozenset(("instrument_navigation",)),
            max_stamina=1000,skill=0.8,
        )
        files=emit_expedition_godot_project(world,native_player)
        out["godot_candidate_proof"]=verify_expedition_godot_project(
            files,world,native_player,
        )
        from skeleton.forge.game_frontier_studio_native_runtime import (
            add_studio_native_gameplay,
        )
        compiled_files=add_studio_native_gameplay(project, files)
        out["godot_project_files"]=compiled_files
        out["studio_native_runtime_installed"]=len(compiled_files)>len(files)
        out["studio_native_runtime_sha256"]=sha256(json.dumps(
            compiled_files, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode("utf-8")).hexdigest()
    out["receipt_digest"]=sha256(json.dumps(
        out,sort_keys=True,separators=(",",":"),allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return out
