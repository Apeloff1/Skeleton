"""Modern RPG creation tools over canonical era-game/Forge owners.

Declarative, portable, no generated executable scripts: multi-layer 2D/3D
map editing, prefabs, actors, class skills, quest flags, dialogue events,
cutscenes, world weather, lighting, fluid, audio and editor operations.
The runtime returns proposals for canonical Godot/engine confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from skeleton.jeeves.game_frontier_production import ERA_TRIANGLE_BUDGETS
from skeleton.forge.game_frontier_rpg_events import RPGEventPage, event_authoring_catalog


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
        pids=[p.prefab_id for p in self.prefabs]
        if len(set(pids))!=len(pids):
            raise StudioError("duplicate prefab")
        if any(p.prefab_id not in pids for p in self.placements):
            raise StudioError("placement must resolve existing prefab")
        events=[x.event_id for x in self.events]
        if len(set(events))!=len(events):
            raise StudioError("duplicate event id")
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
            "soundtrack":self.soundtrack_ids,
            "authority":"candidate_not_executed",
        }


def compile_studio_project(project: StudioProject) -> dict:
    """Produce deterministic editor→engine candidate with hash provenance."""
    m=project.authored_manifest()
    canonical=json.dumps(m,sort_keys=True,separators=(",",":"),allow_nan=False)
    m["content_sha256"]=sha256(canonical.encode()).hexdigest()
    return m


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
