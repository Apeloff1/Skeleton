"""Source-bound canonical narrative director for playable original game worlds.

Dialogs and scenes are original authored data, not scraped literary sources.
A scene may only be performed at a real mapped waypoint and after actually
earned game quest flags/items; a choice can unlock subsequent *story* nodes
but cannot forge gameplay flags or overwrite canonical game-state.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
from typing import Mapping,Sequence
from .game_frontier_expedition import (
    ExpeditionEpisode,ExpeditionError,ExpeditionWorld,_digest,
)

SCHEMA="skeleton.game.canon_dialogue.v1"


@dataclass(frozen=True,slots=True)
class StoryChoice:
    choice_id:str
    spoken_line:str
    advances:tuple[str,...]=()
    consequence:str=""

    def __post_init__(self):
        if not isinstance(self.choice_id,str) or not self.choice_id.isidentifier():
            raise ExpeditionError("choice identity must be canonical")
        if not isinstance(self.spoken_line,str) or not 1<=len(self.spoken_line)<=512:
            raise ExpeditionError("original dialogue requires bounded authored text")
        if not isinstance(self.consequence,str) or len(self.consequence)>512:
            raise ExpeditionError("story consequence cannot be unbounded")
        if type(self.advances) is not tuple or len(self.advances)>16 or len(set(self.advances))!=len(self.advances):
            raise ExpeditionError("story advancement must be explicit and unique")
        if any(not isinstance(x,str) or not x.isidentifier() for x in self.advances):
            raise ExpeditionError("invalid story continuation flag")


@dataclass(frozen=True,slots=True)
class CanonScene:
    scene_id:str
    act:int
    waypoint:str
    speaker:str
    opening:str
    requires_game_flags:tuple[str,...]=()
    requires_story_flags:tuple[str,...]=()
    choices:tuple[StoryChoice,...]=()
    repeatable:bool=False

    def __post_init__(self):
        for value in (self.scene_id,self.waypoint,self.speaker):
            if not isinstance(value,str) or not value.isidentifier():
                raise ExpeditionError("canonical scene identifier invalid")
        if type(self.act) is not int or not 1<=self.act<=1000:
            raise ExpeditionError("story act index must be explicit")
        if not isinstance(self.opening,str) or not 1<=len(self.opening)<=2048:
            raise ExpeditionError("scene opening must be authored and finite")
        if type(self.choices) is not tuple or not 1<=len(self.choices)<=16:
            raise ExpeditionError("scene must contain playable dialogue choices")
        if len({c.choice_id for c in self.choices})!=len(self.choices):
            raise ExpeditionError("duplicate scene choice")
        if (type(self.requires_game_flags) is not tuple
                or type(self.requires_story_flags) is not tuple
                or len(self.requires_game_flags)>64
                or len(self.requires_story_flags)>64):
            raise ExpeditionError("scene prerequisites must be bounded")
        for token in self.requires_game_flags+self.requires_story_flags:
            if not isinstance(token,str) or not token.isidentifier():
                raise ExpeditionError("prerequisite canonical flag invalid")
        if type(self.repeatable) is not bool:
            raise ExpeditionError("scene repeatability must be explicit")


@dataclass(frozen=True,slots=True)
class StoryBook:
    world_digest:str
    gdd_digest:str
    scenes:tuple[CanonScene,...]

    def __post_init__(self):
        for v in (self.world_digest,self.gdd_digest):
            if type(v) is not str or len(v)!=64 or any(c not in "0123456789abcdef" for c in v):
                raise ExpeditionError("story canon needs exact source/GDD digest")
        if type(self.scenes) is not tuple or not 1<=len(self.scenes)<=9999:
            raise ExpeditionError("story scene catalog exceeds original script budget")
        ids=[s.scene_id for s in self.scenes]
        if len(set(ids))!=len(ids):
            raise ExpeditionError("canonical story scene IDs duplicated")
        grants={g for s in self.scenes for c in s.choices for g in c.advances}
        for scene in self.scenes:
            if not isinstance(scene,CanonScene):
                raise ExpeditionError("story scenes require original typed authored source")
            if any(flag not in grants for flag in scene.requires_story_flags):
                raise ExpeditionError("story scene requires a never-produced story flag")

    @property
    def digest(self)->str:
        return _digest(self.as_dict())

    def as_dict(self)->dict:
        return {
            "schema":SCHEMA,"world_digest":self.world_digest,"gdd_digest":self.gdd_digest,
            "scenes":[asdict(x) for x in self.scenes],
        }

    def validate_world(self,world:ExpeditionWorld)->None:
        if not isinstance(world,ExpeditionWorld) or self.world_digest!=world.digest:
            raise ExpeditionError("story authored for another source world")
        for scene in self.scenes:
            if scene.waypoint not in world.by_id:
                raise ExpeditionError("canonical scene refers to nonexistent game location")


@dataclass(frozen=True,slots=True)
class StoryMoment:
    scene_id:str
    choice_id:str
    waypoint:str
    game_receipt:str
    prior_receipt:str
    receipt:str
    outcome:str


class CanonDirector:
    def __init__(self,book:StoryBook,world:ExpeditionWorld):
        if not isinstance(book,StoryBook):
            raise ExpeditionError("actual canonical original story required")
        book.validate_world(world)
        self.book=book
        self.world=world
        self.flags:set[str]=set()
        self.moments:list[StoryMoment]=[]
        self.head=_digest({"world":world.digest,"story":book.digest,"gdd":book.gdd_digest})

    def offered(self,episode:ExpeditionEpisode)->tuple[CanonScene,...]:
        if not isinstance(episode,ExpeditionEpisode) or episode.world.digest!=self.world.digest:
            raise ExpeditionError("narrative must use the exact source game session")
        played={m.scene_id for m in self.moments}
        return tuple(scene for scene in self.book.scenes if (
            scene.waypoint==episode.position
            and (scene.repeatable or scene.scene_id not in played)
            and set(scene.requires_game_flags).issubset(episode.flags|episode.inventory)
            and set(scene.requires_story_flags).issubset(self.flags)
        ))

    def choose(self,episode:ExpeditionEpisode,scene_id:str,choice_id:str)->StoryMoment:
        scene=next((s for s in self.offered(episode) if s.scene_id==scene_id),None)
        if scene is None:
            raise ExpeditionError("dialogue unavailable at current canonical scene")
        choice=next((c for c in scene.choices if c.choice_id==choice_id),None)
        if choice is None:
            raise ExpeditionError("unknown authored dialogue choice")
        # The narrative is read-only against gameplay: flags earned in a
        # conversation never appear in the physics/quests source ledger unless
        # separately earned by actual game actions.
        game_receipt=episode.snapshot()["receipt_head"]
        old=self.head
        data={
            "scene":scene_id,"choice":choice_id,"waypoint":episode.position,
            "story":self.book.digest,"game":game_receipt,"prior":old,
            "consequence":choice.consequence,"flags":list(choice.advances),
        }
        self.head=_digest(data)
        self.flags.update(choice.advances)
        moment=StoryMoment(scene_id,choice_id,episode.position,game_receipt,old,self.head,choice.consequence)
        self.moments.append(moment)
        return moment

    def snapshot(self)->dict:
        data={
            "schema":"skeleton.game.story_continuity.v1",
            "story_digest":self.book.digest,"world_digest":self.world.digest,
            "choices":[{"scene":m.scene_id,"choice":m.choice_id,
                        "game_receipt":m.game_receipt} for m in self.moments],
            "head":self.head,"flags":sorted(self.flags),
        }
        return {**data,"snapshot_digest":_digest(data)}

    @classmethod
    def restore(cls,book:StoryBook,episode:ExpeditionEpisode,checkpoint:Mapping)->"CanonDirector":
        if not isinstance(checkpoint,Mapping) or set(checkpoint)!={
            "schema","story_digest","world_digest","choices","head","flags","snapshot_digest",
        }:
            raise ExpeditionError("story snapshot structure incomplete")
        payload=dict(checkpoint)
        tail=payload.pop("snapshot_digest")
        if tail!=_digest(payload):
            raise ExpeditionError("canonical story checkpoint hash invalid")
        if checkpoint["story_digest"]!=book.digest or checkpoint["world_digest"]!=episode.world.digest:
            raise ExpeditionError("story checkpoint belongs to another canonical game")
        # Narrative replay needs historical game checkpoints for exact proof.
        # Reuse only a zero-choice snapshot here; other choices require the
        # caller to replay corresponding gameplay states first.
        if checkpoint["choices"]:
            raise ExpeditionError("story replay requires full historical gameplay timeline")
        director=cls(book,episode.world)
        if director.head!=checkpoint["head"] or checkpoint["flags"]!=[]:
            raise ExpeditionError("canonical story genesis snapshot changed")
        return director


def original_expedition_story(world:ExpeditionWorld,gdd_digest:str)->StoryBook:
    """Author an original three-act story grounded only in available game nodes."""
    destination=world.destinations[0]
    middle=world.waypoints[1].waypoint_id
    return StoryBook(world.digest,gdd_digest,(
        CanonScene("departure",1,world.arrival,"harbor_keeper",
            "No map tells you which sky is yours. Choose what you will remember.",
            choices=(
                StoryChoice("chart","I will draw the crossings myself.",("map_promised",),"Charting oath"),
                StoryChoice("rescue","I will return for those left below.",("rescue_promised",),"Rescue oath"),
            )),
        CanonScene("threshold",2,middle,"cloud_witness",
            "A floating island remembers the cost of the path that brought you.",
            choices=(
                StoryChoice("remember","I remember every footstep.",("memory_kept",),"Oath witnessed"),
            )),
        CanonScene("arrival",3,destination,"sky_archivist",
            "The horizon has a name now, and your answer will remain in the archive.",
            requires_story_flags=("memory_kept",),
            choices=(
                StoryChoice("archive","Tell the world what I discovered.",("chronicle_written",),"Chronicle founded"),
            )),
    ))
