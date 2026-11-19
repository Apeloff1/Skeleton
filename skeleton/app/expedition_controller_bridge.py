"""Map source-replayed controller transitions to actual ExpeditionEpisode state.

Selection is local UI state. Only explicit travel/rest/inspect commands
invoke the canonical gameplay owner; physical device input is not captured.
"""
from __future__ import annotations
from dataclasses import asdict
from skeleton.app.recovered_evidence import EvidenceError,digest,integer
from skeleton.jeeves.game_frontier_expedition import ExpeditionEpisode,ExpeditionAction,assess_travel
from skeleton.jeeves.game_frontier_expedition_input import GameInput

MAX_INTENTS=256


class Journey:
    def __init__(self,episode):
        if not isinstance(episode,ExpeditionEpisode):
            raise EvidenceError("typed expedition episode required")
        self.episode=episode
        self.selection=0
        self.last_frame=-1
        self.input_sequence=0
        self.records=[]

    def options(self):
        episode=self.episode
        result=[]
        for edge in episode.world.by_edge.values():
            if edge.source!=episode.position:
                continue
            review=assess_travel(episode.world,edge,episode.traveler,current_flags=frozenset(episode.flags))
            if review.allowed and review.stamina<=episode.stamina:
                result.append(edge.edge_id)
        return tuple(sorted(result))

    def current(self):
        options=self.options()
        return options[self.selection%len(options)] if options else None

    def apply(self,event):
        if not isinstance(event,GameInput) or event.sequence!=self.input_sequence+1 or event.frame<=self.last_frame:
            raise EvidenceError("ambiguous or reordered merged input")
        if self.input_sequence>=MAX_INTENTS:
            raise EvidenceError("controller journey input ceiling")
        if self.episode.done:
            raise EvidenceError("controller input after terminal gameplay")
        before=self.current()
        original=self.episode.state()
        action=event.action
        receipt=None
        if action in ("navigate_up","navigate_down"):
            options=self.options()
            if not options:
                raise EvidenceError("no currently admissible outgoing route")
            self.selection=(self.selection+(-1 if action=="navigate_up" else 1))%len(options)
        elif action=="travel":
            if before is None:
                raise EvidenceError("no selected admissible outgoing route")
            receipt=self.episode.step(ExpeditionAction("travel",before))["receipt"]
            self.selection=0
        elif action in ("rest","inspect"):
            receipt=self.episode.step(ExpeditionAction(action))["receipt"]
            self.selection=0
        else:
            raise EvidenceError("unsupported journey controller action")
        self.input_sequence=event.sequence
        self.last_frame=event.frame
        record={"sequence":event.sequence,"frame":event.frame,"action":action,
                "selection_before":before,"selection_after":self.current(),
                "episode_before":digest(original),"episode_after":digest(self.episode.state()),
                "gameplay_receipt":receipt}
        self.records.append(record)
        return record


def semantic_route(episode,route):
    """Author the minimum selection navigation needed for an exact route."""
    journey=Journey(episode)
    actions=[]
    for edge in route.edge_ids:
        options=journey.options()
        if edge not in options:
            raise EvidenceError("route cannot be selected under live stamina/flag state")
        offset=options.index(edge)
        delta=(offset-journey.selection)%len(options)
        if delta<=len(options)-delta:
            moves=["navigate_down"]*delta
        else:
            moves=["navigate_up"]*(len(options)-delta)
        for action in moves+["travel"]:
            if len(actions)>=MAX_INTENTS:
                raise EvidenceError("route exceeds controller journey budget")
            actions.append(action)
            n=len(actions)
            event=GameInput(n,n*4,action,0,"synthetic_authoring","0"*64,"0"*64)
            journey.apply(event)
    if not journey.episode.won:
        raise EvidenceError("canonical authored route failed to reach destination")
    return tuple(actions),journey
