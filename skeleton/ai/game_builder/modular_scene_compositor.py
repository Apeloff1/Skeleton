"""Composable original scene direction: actors, cameras, timelines and LOD.

Consumes authored cutscene cues at exact timestamps and citizen positions
from the shared deterministic society. The output is a render-command model,
not a proprietary rendering engine or an actual video/audio asset.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .contracts import canonical_digest
from .quest_scene_engine import DirectorWorld, Cutscene, Scene, DirectorError
from .npc_society_runtime import Society
from .director_capability_graph import TIERS


class CompositionError(ValueError):
    """Director scene graph is incoherent, unsupported or over hardware budget."""


@dataclass(frozen=True, slots=True)
class Transform:
    x: int = 0
    y: int = 0
    z: int = 0
    orientation: int = 0
    scale: int = 100

    def __post_init__(self):
        for key, bound in ((self.x,100000),(self.y,100000),
                           (self.z,100000),(self.orientation,360),
                           (self.scale,1000)):
            if type(key) is not int or not -bound<=key<=bound:
                raise CompositionError("out-of-bounds original spatial transform")
        if self.scale<=0:
            raise CompositionError("actors cannot have zero or negative scaling")

    def payload(self):
        return dict(x=self.x,y=self.y,z=self.z,orientation=self.orientation,
                    scale=self.scale)


@dataclass(frozen=True, slots=True)
class StageActor:
    key: str
    role: str
    transform: Transform
    visible: bool
    semantic_label: str
    entity_source: str
    expression: str = "neutral"

    def payload(self):
        return dict(key=self.key,role=self.role,
                    transform=self.transform.payload(),
                    visible=self.visible,semantic_label=self.semantic_label,
                    entity_source=self.entity_source,expression=self.expression)


@dataclass(frozen=True, slots=True)
class StageFrame:
    world_digest: str
    scene: str
    cutscene: str | None
    at_ms: int
    camera: str
    lighting: str
    weather: str
    audio_cues: tuple[str,...]
    subtitle: str
    actors: tuple[StageActor,...]
    props: tuple[str,...]
    active_cues: tuple[str,...]
    visible_npcs: int
    dormant_npcs_outside_view: int
    tier: str
    source_cutscene_digest: str | None

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.director_frame.v1",
                    world_digest=self.world_digest,scene=self.scene,
                    cutscene=self.cutscene,at_ms=self.at_ms,
                    camera=self.camera,lighting=self.lighting,
                    weather=self.weather,audio_cues=list(self.audio_cues),
                    subtitle=self.subtitle,
                    actors=[a.payload() for a in self.actors],
                    props=list(self.props),active_cues=list(self.active_cues),
                    visible_npcs=self.visible_npcs,
                    dormant_npcs_outside_view=self.dormant_npcs_outside_view,
                    tier=self.tier,source_cutscene_digest=self.source_cutscene_digest,
                    renderer_2d_or_3d_verified=False,
                    audio_playback_verified=False)


def _stage_cast(scene: Scene,society: Society,*,actor_limit: int):
    actors=[]
    for i,role in enumerate(scene.cast):
        actors.append(StageActor(
            role,role,Transform(i*160,0,i%2*20),
            True,role,"scene_author",
        ))
    for index,(profile,mind) in enumerate(zip(society.profiles,society.minds)):
        if mind.scene!=scene.key or mind.lod=="dormant":
            continue
        if len(actors)>=actor_limit:
            break
        actors.append(StageActor(
            profile.key,profile.profession,
            Transform((index%12)*85,(index//12)*75,0),
            True,profile.name,"observed_npc_society",mind.intent,
        ))
    return actors


def compose_scene(
    world: DirectorWorld,society: Society,scene_key: str, *,
    cutscene_key: str | None = None,at_ms: int = 0,
    tier: str = "desktop",authorized: bool,
) -> StageFrame:
    if not authorized:
        raise PermissionError("render command composition requires operator authority")
    if not isinstance(world,DirectorWorld) or not isinstance(society,Society):
        raise CompositionError("original scene and NPC population required")
    if society.world_digest!=world.digest:
        raise CompositionError("scene cannot stage foreign NPC memories/positions")
    if tier not in TIERS:
        raise CompositionError("unrecognized consumer rendering tier")
    if type(at_ms) is not int or not 0<=at_ms<=120000:
        raise CompositionError("cinematic sampling exceeds bounded timeline")
    original=next((s for s in world.scenes if s.key==scene_key),None)
    if original is None:
        raise CompositionError("no such original scene")
    selected=None
    if cutscene_key is not None:
        selected=next((c for c in original.cutscenes if c.key==cutscene_key),None)
        if selected is None:
            raise CompositionError("timeline belongs to a different scene")
    tier_spec=TIERS[tier]
    actors=_stage_cast(original,society,actor_limit=tier_spec.actor_budget)
    by_key={a.key:i for i,a in enumerate(actors)}
    camera=original.camera
    lighting=original.lighting
    weather=original.weather
    audio=[original.music]
    subtitle=""
    active=[]
    if selected is not None:
        if len(selected.cues)>tier_spec.cue_budget:
            raise CompositionError("cinematic cues exceed device-specific budget")
        for cue in selected.cues:
            if cue.at>at_ms:
                break
            active.append(cue.kind+":"+cue.target)
            if cue.kind in {
                "camera_cut","camera_pan","camera_track","camera_dolly",
                "camera_zoom","camera_shake","focus",
            }:
                camera=cue.value
            elif cue.kind in {"lighting","color_grade"}:
                lighting=cue.value
            elif cue.kind=="weather":
                weather=cue.value
            elif cue.kind in {"voice_cue","music_cue","sound_cue","ambient_cue"}:
                audio.append(cue.value)
            elif cue.kind in {"subtitle","dialogue","objective_reveal","ui_prompt"}:
                subtitle=cue.value
            elif cue.kind in {"actor_move","actor_enter","actor_exit",
                               "actor_pose","actor_emote","animation"}:
                index=by_key.get(cue.target)
                if index is None:
                    # Cast outside this scene must never be teleported in by
                    # timeline text. Record the cue but do not invent an NPC.
                    continue
                before=actors[index]
                if cue.kind=="actor_move":
                    movement=replace(before.transform,x=before.transform.x+80,
                                     y=before.transform.y+20)
                    actors[index]=replace(before,transform=movement)
                elif cue.kind=="actor_enter":
                    actors[index]=replace(before,visible=True)
                elif cue.kind=="actor_exit":
                    actors[index]=replace(before,visible=False)
                else:
                    actors[index]=replace(before,expression=cue.value)
    total_in_scene=sum(m.scene==scene_key for m in society.minds)
    actual_npcs=sum(a.entity_source=="observed_npc_society" for a in actors)
    return StageFrame(
        world.digest,scene_key,cutscene_key,at_ms,camera,lighting,weather,
        tuple(audio),subtitle,tuple(actors),original.props,
        tuple(active),actual_npcs,
        max(0,len(society.minds)-actual_npcs),tier,
        canonical_digest(selected.payload()) if selected else None,
    )


def storyboard(
    world: DirectorWorld,society: Society,scene_key: str,cutscene_key: str, *,
    tier: str="desktop",authorized: bool,
) -> tuple[StageFrame,...]:
    if not authorized:
        raise PermissionError("storyboarding requires authored approval")
    scene=next((s for s in world.scenes if s.key==scene_key),None)
    if scene is None:
        raise CompositionError("storyboard references unavailable scene")
    cinematic=next((c for c in scene.cutscenes if c.key==cutscene_key),None)
    if cinematic is None:
        raise CompositionError("unknown original cutscene")
    times=tuple(sorted({0,*(cue.at for cue in cinematic.cues),
                        *(cue.at+cue.duration for cue in cinematic.cues)}))
    if len(times)>512:
        raise CompositionError("cutscene storyboard must be bounded")
    frames=tuple(compose_scene(world,society,scene_key,cutscene_key=cutscene_key,
                              at_ms=at,tier=tier,authorized=True)
                 for at in times)
    if any(frame.world_digest!=world.digest for frame in frames):
        raise CompositionError("scene storyboard changed authored source")
    return frames


__all__=[
    "CompositionError","Transform","StageActor","StageFrame",
    "compose_scene","storyboard",
]
