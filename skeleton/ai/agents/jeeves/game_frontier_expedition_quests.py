"""Consequence-aware original game quest lines and deterministic alternate endings.

Quest progression is driven by real movement, collected game items and
source-bound dialogue receipts. Outcomes are never substituted for world
playthroughs, and all endings have concrete independent replay checks.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Mapping

from .game_frontier_expedition import ExpeditionEpisode, ExpeditionError, _digest
from .game_frontier_expedition_narrative import CanonDirector, StoryBook

SCHEMA = "skeleton.game.canon_quest_endings.v1"


@dataclass(frozen=True, slots=True)
class QuestStage:
    stage_id: str
    waypoint: str
    requires_game_flags: tuple[str, ...] = ()
    requires_items: tuple[str, ...] = ()
    requires_story_flags: tuple[str, ...] = ()
    unlocks: tuple[str, ...] = ()
    optional: bool = False

    def __post_init__(self):
        for token in (self.stage_id, self.waypoint) + self.requires_game_flags + self.requires_items + self.requires_story_flags + self.unlocks:
            if not isinstance(token, str) or not token.isidentifier():
                raise ExpeditionError("quest stage requires canonical identities")
        for group in (self.requires_game_flags, self.requires_items,
                      self.requires_story_flags, self.unlocks):
            if type(group) is not tuple or len(group) > 64 or len(set(group)) != len(group):
                raise ExpeditionError("quest prerequisites cannot duplicate or overflow")
        if type(self.optional) is not bool:
            raise ExpeditionError("quest optionality must be explicit")


@dataclass(frozen=True, slots=True)
class Quest:
    quest_id: str
    stages: tuple[QuestStage, ...]
    repeatable: bool = False

    def __post_init__(self):
        if not isinstance(self.quest_id, str) or not self.quest_id.isidentifier():
            raise ExpeditionError("quest identifier is not canonical")
        if type(self.stages) is not tuple or not 1 <= len(self.stages) <= 256:
            raise ExpeditionError("quest has no finite playable stages")
        if len({s.stage_id for s in self.stages}) != len(self.stages):
            raise ExpeditionError("duplicate quest stage")
        if type(self.repeatable) is not bool:
            raise ExpeditionError("quest repeatability not explicit")


@dataclass(frozen=True, slots=True)
class Ending:
    ending_id: str
    title: str
    needs_game_flags: tuple[str, ...] = ()
    needs_story_flags: tuple[str, ...] = ()
    needs_quest_flags: tuple[str, ...] = ()
    priority: int = 0

    def __post_init__(self):
        if not isinstance(self.ending_id, str) or not self.ending_id.isidentifier():
            raise ExpeditionError("ending id invalid")
        if not isinstance(self.title, str) or not 1 <= len(self.title) <= 256:
            raise ExpeditionError("ending needs an original description")
        if type(self.priority) is not int or not 0 <= self.priority <= 100:
            raise ExpeditionError("ending priority invalid")
        for tokens in (self.needs_game_flags,self.needs_story_flags,self.needs_quest_flags):
            if type(tokens) is not tuple or len(tokens)>64 or any(
                not isinstance(k,str) or not k.isidentifier() for k in tokens
            ):
                raise ExpeditionError("ending prerequisite invalid")


@dataclass(frozen=True, slots=True)
class QuestBook:
    world_digest: str
    story_digest: str
    quests: tuple[Quest, ...]
    endings: tuple[Ending, ...]

    def __post_init__(self):
        for item in (self.world_digest,self.story_digest):
            if type(item) is not str or len(item) != 64 or any(c not in "0123456789abcdef" for c in item):
                raise ExpeditionError("quest book must bind authoritative source")
        if not isinstance(self.quests,tuple) or not 1 <= len(self.quests) <= 128:
            raise ExpeditionError("quest book size invalid")
        if not isinstance(self.endings,tuple) or not 2 <= len(self.endings) <= 32:
            raise ExpeditionError("multiple authored endings required")
        if len({q.quest_id for q in self.quests}) != len(self.quests) or len(
            {e.ending_id for e in self.endings}) != len(self.endings):
            raise ExpeditionError("duplicate quest or ending identity")
        possible = {g for q in self.quests for s in q.stages for g in s.unlocks}
        if any(flag not in possible for ending in self.endings for flag in ending.needs_quest_flags):
            raise ExpeditionError("ending depends on impossible quest proof")

    @property
    def digest(self):
        return _digest(self.as_dict())

    def as_dict(self):
        return {"schema":SCHEMA,"world":self.world_digest,"story":self.story_digest,
                "quests":[asdict(q) for q in self.quests],
                "endings":[asdict(e) for e in self.endings]}


class QuestDirector:
    def __init__(self,book:QuestBook,story:CanonDirector,episode:ExpeditionEpisode):
        if not isinstance(book,QuestBook) or not isinstance(story,CanonDirector) or not isinstance(episode,ExpeditionEpisode):
            raise ExpeditionError("quest requires source-bound story and real gameplay")
        if (book.world_digest != episode.world.digest or
                book.story_digest != story.book.digest):
            raise ExpeditionError("quest cannot use mismatched world/story")
        if any(stage.waypoint not in episode.world.by_id for q in book.quests for stage in q.stages):
            raise ExpeditionError("quest references missing authored region")
        self.book=book
        self.flags:set[str]=set()
        self.progress={q.quest_id:0 for q in book.quests}
        self.events:list[dict]=[]
        self.head=_digest({"book":book.digest,"world":episode.world.digest})

    def advance(self,episode:ExpeditionEpisode,story:CanonDirector)->tuple[dict,...]:
        if (not isinstance(episode,ExpeditionEpisode) or episode.world.digest!=self.book.world_digest
                or not isinstance(story,CanonDirector) or story.book.digest!=self.book.story_digest):
            raise ExpeditionError("quest progression requires unchanged game and canon")
        generated=[]
        for quest in self.book.quests:
            index=self.progress[quest.quest_id]
            if index>=len(quest.stages):
                continue
            stage=quest.stages[index]
            if not (
                episode.position==stage.waypoint
                and set(stage.requires_game_flags).issubset(episode.flags)
                and set(stage.requires_items).issubset(episode.inventory)
                and set(stage.requires_story_flags).issubset(story.flags)
            ):
                continue
            old=self.head
            evidence={
                "quest":quest.quest_id,"stage":stage.stage_id,
                "step":index+1,"game_receipt":episode.snapshot()["receipt_head"],
                "story_receipt":story.head,"previous":old,"source":self.book.digest,
                "unlocks":list(stage.unlocks),
            }
            self.head=_digest(evidence)
            self.flags.update(stage.unlocks)
            self.progress[quest.quest_id]=index+1
            record={**evidence,"receipt":self.head}
            self.events.append(record)
            generated.append(record)
        return tuple(generated)

    def ending(self,episode:ExpeditionEpisode,story:CanonDirector)->dict:
        if (episode.world.digest!=self.book.world_digest or story.book.digest!=self.book.story_digest):
            raise ExpeditionError("ending cannot use foreign gameplay")
        if not episode.won:
            raise ExpeditionError("ending cannot occur without completing actual game")
        choices=[e for e in self.book.endings if (
            set(e.needs_game_flags).issubset(episode.flags | episode.inventory)
            and set(e.needs_story_flags).issubset(story.flags)
            and set(e.needs_quest_flags).issubset(self.flags)
        )]
        if not choices:
            raise ExpeditionError("no authored ending matches actual player choices")
        chosen=sorted(choices,key=lambda e:(-e.priority,e.ending_id))[0]
        report={
            "schema":"skeleton.game.canon_ending_receipt.v1",
            "ending_id":chosen.ending_id,"title":chosen.title,
            "source":self.book.digest,"game_receipt":episode.snapshot()["receipt_head"],
            "story_receipt":story.head,"quest_receipt":self.head,
            "victory":episode.won,"quest_flags":sorted(self.flags),
        }
        return {**report,"receipt_digest":_digest(report)}

    def snapshot(self)->dict:
        payload={"schema":"skeleton.game.quest_progression.v1",
                 "source":self.book.digest,"progress":dict(self.progress),
                 "flags":sorted(self.flags),"events":list(self.events),"head":self.head}
        return {**payload,"snapshot_digest":_digest(payload)}


def original_quest_book(episode:ExpeditionEpisode,story:StoryBook)->QuestBook:
    if not isinstance(episode,ExpeditionEpisode) or not isinstance(story,StoryBook) or story.world_digest!=episode.world.digest:
        raise ExpeditionError("quest authoring needs linked gameplay and story")
    world=episode.world
    first=world.waypoints[1].waypoint_id
    destination=world.destinations[0]
    quest=Quest("chart_the_islands",(
        QuestStage("accept",world.arrival,requires_story_flags=("map_promised",),
                   unlocks=("chart_contract",)),
        QuestStage("survey",first,requires_game_flags=(f"charted_islet_001",),
                   unlocks=("surveyed_first_island",)),
        QuestStage("finish",destination,requires_story_flags=("memory_kept",),
                   unlocks=("completed_chart",)),
    ))
    rescue=Quest("keep_the_promise",(
        QuestStage("accept_rescue",world.arrival,requires_story_flags=("rescue_promised",),
                   unlocks=("rescue_oath",)),
        QuestStage("reach",first,unlocks=("first_refuge_reached",)),
        QuestStage("complete",destination,unlocks=("return_routes_known",)),
    ),repeatable=False)
    return QuestBook(world.digest,story.digest,(quest,rescue),(
        Ending("cartographer","The Sky Atlas Is Open",
               needs_story_flags=("map_promised","memory_kept"),
               needs_quest_flags=("completed_chart",),priority=90),
        Ending("rescuer","A Way Home For Everyone",
               needs_story_flags=("rescue_promised","memory_kept"),
               needs_quest_flags=("return_routes_known",),priority=90),
        Ending("wanderer","A New Horizon",priority=1),
    ))
