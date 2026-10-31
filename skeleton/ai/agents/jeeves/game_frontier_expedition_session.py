"""One authoritative, replayable game/story/quest production session.

Every input is a real ExpeditionEpisode action or a canon-authorized spoken
choice. Quest advancement is re-derived after the input and the complete
gameplay/story/quest state is hashed in a serial action receipt. Restoring
requires independent re-execution of *every* action; no stored flags are trusted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionWorld, Traveler, ExpeditionEpisode, ExpeditionAction,
    ExpeditionError, _digest, _json,
)
from .game_frontier_expedition_narrative import (
    StoryBook, CanonDirector,
)
from .game_frontier_expedition_quests import (
    QuestBook, QuestDirector,
)

SCHEMA="skeleton.game.production_session.v1"
MAX_EVENTS=4096


@dataclass(frozen=True, slots=True)
class ProductionInput:
    kind: str
    action_kind: str = ""
    edge_id: str = ""
    scene_id: str = ""
    choice_id: str = ""

    def __post_init__(self):
        if self.kind not in ("gameplay", "dialogue"):
            raise ExpeditionError("production input requires gameplay or authored dialogue")
        for name in ("action_kind","edge_id","scene_id","choice_id"):
            if type(getattr(self,name)) is not str or len(getattr(self,name))>128:
                raise ExpeditionError("production input field out of bounds")
        if self.kind=="gameplay":
            if not self.action_kind or self.scene_id or self.choice_id:
                raise ExpeditionError("game action cannot impersonate a story choice")
        elif not self.scene_id or not self.choice_id or self.action_kind or self.edge_id:
            raise ExpeditionError("story choice cannot impersonate actual game action")

    def as_dict(self)->dict:
        return {
            "kind":self.kind,"action_kind":self.action_kind,"edge_id":self.edge_id,
            "scene_id":self.scene_id,"choice_id":self.choice_id,
        }


class ProductionSession:
    def __init__(self,world:ExpeditionWorld,player:Traveler,
                 storybook:StoryBook,questbook:QuestBook):
        if (not isinstance(world,ExpeditionWorld) or not isinstance(player,Traveler)
                or not isinstance(storybook,StoryBook) or not isinstance(questbook,QuestBook)):
            raise ExpeditionError("game session requires typed original source")
        if storybook.world_digest!=world.digest:
            raise ExpeditionError("narrative continuity belongs to a foreign game")
        if (questbook.world_digest!=world.digest
                or questbook.story_digest!=storybook.digest):
            raise ExpeditionError("quest continuity belongs to a foreign story")
        self.game=ExpeditionEpisode(world,player)
        self.story=CanonDirector(storybook,world)
        self.quests=QuestDirector(questbook,self.story,self.game)
        self.events:list[dict]=[]
        self.head=_digest({
            "schema":SCHEMA,"world":world.digest,
            "player":self.game.traveler_digest,
            "story":storybook.digest,"quest":questbook.digest,
            "genesis":True,
        })

    def submit(self,entry:ProductionInput)->dict:
        if not isinstance(entry,ProductionInput):
            raise ExpeditionError("production session requires typed original input")
        if len(self.events)>=MAX_EVENTS:
            raise ExpeditionError("production sequence exceeded replay capacity")
        before=self.head
        game_before=self.game.snapshot()["receipt_head"]
        story_before=self.story.head
        if entry.kind=="gameplay":
            event=self.game.step(ExpeditionAction(entry.action_kind,entry.edge_id))
            result_receipt=event["receipt"]
        else:
            choice=self.story.choose(self.game,entry.scene_id,entry.choice_id)
            result_receipt=choice.receipt
        quest_updates=self.quests.advance(self.game,self.story)
        record={
            "sequence":len(self.events)+1,
            "input":entry.as_dict(),
            "previous":before,
            "world":self.game.world.digest,
            "game_before":game_before,
            "game_after":self.game.snapshot()["receipt_head"],
            "story_before":story_before,
            "story_after":self.story.head,
            "quest_after":self.quests.head,
            "quest_updates":[event["receipt"] for event in quest_updates],
            "action_receipt":result_receipt,
            "position":self.game.position,
            "health":self.game.health,
            "won":self.game.won,
        }
        self.head=_digest(record)
        result={**record,"receipt":self.head}
        self.events.append(result)
        return result

    def ending(self)->dict:
        result=self.quests.ending(self.game,self.story)
        return {**result,"session_receipt":self.head}

    def snapshot(self)->dict:
        payload={
            "schema":SCHEMA,
            "world_digest":self.game.world.digest,
            "traveler_digest":self.game.traveler_digest,
            "story_digest":self.story.book.digest,
            "quest_digest":self.quests.book.digest,
            "events":list(self.events),
            "game":self.game.snapshot(),
            "story":self.story.snapshot(),
            "quests":self.quests.snapshot(),
            "head":self.head,
            "completed":self.game.won,
        }
        return {**payload,"snapshot_digest":_digest(payload)}

    @classmethod
    def restore(cls, world:ExpeditionWorld, player:Traveler,
                storybook:StoryBook,questbook:QuestBook,
                snapshot:Mapping)->"ProductionSession":
        if not isinstance(snapshot,Mapping) or set(snapshot)!={
            "schema","world_digest","traveler_digest","story_digest",
            "quest_digest","events","game","story","quests","head",
            "completed","snapshot_digest",
        }:
            raise ExpeditionError("production session snapshot schema missing")
        payload={k:v for k,v in snapshot.items() if k!="snapshot_digest"}
        _json(payload,4_000_000)
        if snapshot["snapshot_digest"]!=_digest(payload):
            raise ExpeditionError("production session root checksum mismatch")
        instance=cls(world,player,storybook,questbook)
        if (snapshot["schema"]!=SCHEMA or
                snapshot["world_digest"]!=world.digest or
                snapshot["traveler_digest"]!=instance.game.traveler_digest or
                snapshot["story_digest"]!=storybook.digest or
                snapshot["quest_digest"]!=questbook.digest):
            raise ExpeditionError("production restore references foreign source")
        records=snapshot["events"]
        if type(records) is not list or len(records)>MAX_EVENTS:
            raise ExpeditionError("game session action ledger is unbounded")
        for row in records:
            if type(row) is not dict or "input" not in row or type(row["input"]) is not dict:
                raise ExpeditionError("production session history event malformed")
            candidate=ProductionInput(**row["input"])
            checked=instance.submit(candidate)
            if checked!=row:
                raise ExpeditionError("production session was edited after execution")
        if (instance.game.snapshot()!=snapshot["game"]
                or instance.story.snapshot()!=snapshot["story"]
                or instance.quests.snapshot()!=snapshot["quests"]
                or instance.head!=snapshot["head"]
                or instance.game.won is not snapshot["completed"]):
            raise ExpeditionError("production replay diverged from game/story/quest canon")
        return instance


def verify_production_session(world:ExpeditionWorld, player:Traveler,
                              storybook:StoryBook,questbook:QuestBook,
                              snapshot:Mapping)->dict:
    instance=ProductionSession.restore(world,player,storybook,questbook,snapshot)
    return {
        "schema":"skeleton.game.production_session_verified.v1",
        "world_digest":world.digest,
        "event_count":len(instance.events),
        "game_action_count":len(instance.game.actions),
        "story_choice_count":len(instance.story.moments),
        "quest_event_count":len(instance.quests.events),
        "session_head":instance.head,
        "won":instance.game.won,
        "source_replay_verified":True,
        "release_approved":False,
    }
