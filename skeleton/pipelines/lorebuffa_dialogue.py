"""Stateful dialogue runtime for the Lorebuffa domain pack.

The imported Lorebuffa pack contains a compact Marina dialogue branch. This
module promotes that data into a closed, validated runtime with deterministic
state transitions, requirement gates, side effects, replay, and quest handling.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from skeleton.content.lorebuffa import MARINA_DIALOGUE
from skeleton.kernel.errors import ValidationError


# Complete the deliberately compact source branch without mutating canonical
# imported content. Every destination advertised by MARINA_DIALOGUE becomes
# traversable.
_MARINA_COMPLETION: dict[str, dict[str, Any]] = {
    "trade_menu": {
        "text": "Marina opens the Goldscale ledger and quotes the current harbor rates.",
        "options": [
            {"id": "finish_trade", "text": "Finish trading.", "next": "farewell_warm", "rep_change": 1},
            {"id": "ask_james", "text": "Ask about James before leaving.", "next": "james_mention", "rep_change": 2},
        ],
    },
    "appraisal_offer": {
        "text": "Marina offers a careful appraisal and explains what provenance changes the value.",
        "options": [
            {"id": "accept_appraisal", "text": "Accept the appraisal.", "next": "farewell_warm", "rep_change": 2},
            {"id": "decline_appraisal", "text": "Decline for now.", "next": "farewell_cold", "rep_change": 0},
        ],
    },
    "farewell_cold": {
        "text": "Marina nods once and returns to her ledger.",
        "options": [],
    },
    "farewell_warm": {
        "text": "Marina thanks you for the business and invites you to return.",
        "options": [],
    },
    "disappointed_hope": {
        "text": "Marina looks disappointed, then asks you to tell her if you learn more.",
        "options": [
            {"id": "promise", "text": "Promise to keep looking.", "next": "farewell_warm", "rep_change": 3},
            {"id": "leave", "text": "Leave it there.", "next": "farewell_cold", "rep_change": 0},
        ],
    },
    "demands_details": {
        "text": "Marina spots the holes in the story and demands details you cannot provide.",
        "rewards": {"trust_level": "low"},
        "options": [
            {"id": "admit_lie", "text": "Admit that you lied.", "next": "farewell_cold", "rep_change": -15},
            {"id": "double_down", "text": "Double down on the lie.", "next": "farewell_cold", "rep_change": -25},
        ],
    },
    "marina_determined": {
        "text": "Marina studies the currents and decides a rescue attempt is possible.",
        "options": [
            {"id": "plan_rescue", "text": "Plan the rescue together.", "next": "rescue_mission_planning", "rep_change": 5},
            {"id": "not_yet", "text": "Say you are not ready yet.", "next": "farewell_warm", "rep_change": 0},
        ],
    },
}


def completed_marina_dialogue() -> dict[str, dict[str, Any]]:
    """Return an isolated, closed version of the imported Marina graph."""
    graph = deepcopy(MARINA_DIALOGUE)
    for node_id, node in _MARINA_COMPLETION.items():
        graph.setdefault(node_id, deepcopy(node))
    return graph


@dataclass
class LorebuffaDialogueState:
    """Mutable state for one dialogue session."""

    node_id: str = "greeting"
    reputation: int = 0
    trust_level: str = "neutral"
    inventory: set[str] = field(default_factory=set)
    quests: set[str] = field(default_factory=set)
    knowledge: set[str] = field(default_factory=set)
    factions: set[str] = field(default_factory=set)
    claimed_rewards: set[str] = field(default_factory=set)
    history: list[dict[str, Any]] = field(default_factory=list)
    ended: bool = False

    def snapshot(self) -> dict[str, Any]:
        """Return a stable JSON-compatible session snapshot."""
        return {
            "node_id": self.node_id,
            "reputation": self.reputation,
            "trust_level": self.trust_level,
            "inventory": sorted(self.inventory),
            "quests": sorted(self.quests),
            "knowledge": sorted(self.knowledge),
            "factions": sorted(self.factions),
            "claimed_rewards": sorted(self.claimed_rewards),
            "history": deepcopy(self.history),
            "ended": self.ended,
        }


@dataclass(frozen=True)
class LorebuffaDialogueTurn:
    """Serializable view returned when a conversation is rendered or advanced."""

    node_id: str
    text: str
    options: tuple[dict[str, Any], ...]
    quest_offer: dict[str, Any] | None
    state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "text": self.text,
            "options": [deepcopy(option) for option in self.options],
            "quest_offer": deepcopy(self.quest_offer),
            "state": deepcopy(self.state),
        }


class LorebuffaDialogueRuntime:
    """Execute a Lorebuffa dialogue graph as deterministic game state."""

    def __init__(
        self,
        graph: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        start_node: str = "greeting",
    ) -> None:
        self._graph = deepcopy(dict(graph)) if graph is not None else completed_marina_dialogue()
        self.start_node = start_node
        self.validate_graph(self._graph, start_node=start_node)

    @property
    def graph(self) -> dict[str, dict[str, Any]]:
        """Return a defensive copy so callers cannot corrupt the runtime."""
        return deepcopy(self._graph)

    @classmethod
    def validate_graph(
        cls,
        graph: Mapping[str, Mapping[str, Any]],
        *,
        start_node: str = "greeting",
    ) -> None:
        if not graph:
            raise ValidationError("dialogue graph must not be empty")
        if start_node not in graph:
            raise ValidationError(
                "dialogue start node does not exist",
                context={"start_node": start_node},
            )

        dangling: list[dict[str, str]] = []
        for node_id, node in graph.items():
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValidationError("dialogue node ids must be non-empty strings")
            if not isinstance(node, Mapping):
                raise ValidationError(
                    "dialogue node must be a mapping",
                    context={"node_id": node_id},
                )
            text = node.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValidationError(
                    "dialogue node text must be non-empty",
                    context={"node_id": node_id},
                )
            options = node.get("options", [])
            if not isinstance(options, list):
                raise ValidationError(
                    "dialogue node options must be a list",
                    context={"node_id": node_id},
                )

            seen: set[str] = set()
            for option in options:
                if not isinstance(option, Mapping):
                    raise ValidationError(
                        "dialogue option must be a mapping",
                        context={"node_id": node_id},
                    )
                option_id = option.get("id")
                target = option.get("next")
                if not isinstance(option_id, str) or not option_id.strip():
                    raise ValidationError(
                        "dialogue option id must be non-empty",
                        context={"node_id": node_id},
                    )
                if option_id in seen:
                    raise ValidationError(
                        "dialogue option ids must be unique per node",
                        context={"node_id": node_id, "option_id": option_id},
                    )
                seen.add(option_id)
                if not isinstance(target, str) or not target.strip():
                    raise ValidationError(
                        "dialogue option must name a next node",
                        context={"node_id": node_id, "option_id": option_id},
                    )
                if target not in graph:
                    dangling.append({"node": node_id, "choice": option_id, "target": target})

                rep_change = option.get("rep_change", 0)
                if isinstance(rep_change, bool) or not isinstance(rep_change, int):
                    raise ValidationError(
                        "rep_change must be an integer",
                        context={"node_id": node_id, "option_id": option_id},
                    )
                required = option.get("requires_item")
                if required is not None and (
                    not isinstance(required, str) or not required.strip()
                ):
                    raise ValidationError(
                        "requires_item must be a non-empty string",
                        context={"node_id": node_id, "option_id": option_id},
                    )

        if dangling:
            raise ValidationError(
                "dialogue graph contains dangling destinations",
                context={"dangling": dangling},
            )

    def new_state(
        self,
        *,
        inventory: Iterable[str] = (),
        reputation: int = 0,
        trust_level: str = "neutral",
        node_id: str | None = None,
    ) -> LorebuffaDialogueState:
        selected = node_id or self.start_node
        if selected not in self._graph:
            raise ValidationError(
                "dialogue state starts at an unknown node",
                context={"node_id": selected},
            )
        state = LorebuffaDialogueState(
            node_id=selected,
            reputation=int(reputation),
            trust_level=str(trust_level),
            inventory={str(item).strip() for item in inventory if str(item).strip()},
        )
        self._apply_node_rewards(state, selected)
        state.ended = not bool(self._graph[selected].get("options", []))
        return state

    def start(
        self, state: LorebuffaDialogueState | None = None
    ) -> LorebuffaDialogueTurn:
        current = state or self.new_state()
        self._ensure_state(current)
        return self._turn(current)

    def available_options(
        self, state: LorebuffaDialogueState
    ) -> tuple[dict[str, Any], ...]:
        self._ensure_state(state)
        rendered: list[dict[str, Any]] = []
        for raw in self._graph[state.node_id].get("options", []):
            option = deepcopy(dict(raw))
            required = option.get("requires_item")
            enabled = required is None or required in state.inventory
            option["enabled"] = enabled
            if not enabled:
                option["blocked_reason"] = f"requires_item:{required}"
            rendered.append(option)
        return tuple(rendered)

    def choose(
        self, state: LorebuffaDialogueState, choice_id: str
    ) -> LorebuffaDialogueTurn:
        self._ensure_state(state)
        if state.ended:
            raise ValidationError(
                "dialogue has already ended",
                context={"node_id": state.node_id},
            )

        node = self._graph[state.node_id]
        choice = next(
            (
                option
                for option in node.get("options", [])
                if option.get("id") == choice_id
            ),
            None,
        )
        if choice is None:
            raise ValidationError(
                "dialogue choice does not exist at the current node",
                context={"node_id": state.node_id, "choice_id": choice_id},
            )

        required = choice.get("requires_item")
        if required and required not in state.inventory:
            raise ValidationError(
                "dialogue choice requirement is not satisfied",
                context={
                    "node_id": state.node_id,
                    "choice_id": choice_id,
                    "requires_item": required,
                },
            )

        origin = state.node_id
        target = str(choice["next"])
        rep_delta = int(choice.get("rep_change", 0))
        state.reputation += rep_delta
        self._apply_effects(state, choice)
        state.node_id = target
        self._apply_node_rewards(state, target)
        state.ended = not bool(self._graph[target].get("options", []))
        state.history.append(
            {
                "from": origin,
                "choice": choice_id,
                "to": target,
                "reputation_delta": rep_delta,
                "reputation": state.reputation,
            }
        )
        return self._turn(state)

    def accept_quest(
        self,
        state: LorebuffaDialogueState,
        quest_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_state(state)
        offer = self._graph[state.node_id].get("quest_offer")
        if not isinstance(offer, Mapping):
            raise ValidationError(
                "current dialogue node has no quest offer",
                context={"node_id": state.node_id},
            )
        offered_id = str(offer.get("id") or "").strip()
        if not offered_id:
            raise ValidationError(
                "quest offer has no id",
                context={"node_id": state.node_id},
            )
        if quest_id is not None and quest_id != offered_id:
            raise ValidationError(
                "requested quest is not offered at the current node",
                context={"requested": quest_id, "offered": offered_id},
            )
        state.quests.add(offered_id)
        state.history.append(
            {"event": "quest_accepted", "node": state.node_id, "quest": offered_id}
        )
        return deepcopy(dict(offer))

    def grant_item(self, state: LorebuffaDialogueState, item_id: str) -> None:
        self._ensure_state(state)
        item = str(item_id).strip()
        if not item:
            raise ValidationError("item id must be non-empty")
        state.inventory.add(item)

    def revoke_item(self, state: LorebuffaDialogueState, item_id: str) -> None:
        self._ensure_state(state)
        state.inventory.discard(str(item_id).strip())

    def replay(
        self,
        choices: Iterable[str],
        *,
        inventory: Iterable[str] = (),
        reputation: int = 0,
        trust_level: str = "neutral",
    ) -> LorebuffaDialogueState:
        """Rebuild a session deterministically from choice ids."""
        state = self.new_state(
            inventory=inventory,
            reputation=reputation,
            trust_level=trust_level,
        )
        for choice_id in choices:
            self.choose(state, str(choice_id))
        return state

    def _turn(self, state: LorebuffaDialogueState) -> LorebuffaDialogueTurn:
        node = self._graph[state.node_id]
        offer = node.get("quest_offer")
        return LorebuffaDialogueTurn(
            node_id=state.node_id,
            text=str(node["text"]),
            options=self.available_options(state),
            quest_offer=deepcopy(dict(offer)) if isinstance(offer, Mapping) else None,
            state=state.snapshot(),
        )

    def _ensure_state(self, state: LorebuffaDialogueState) -> None:
        if not isinstance(state, LorebuffaDialogueState):
            raise ValidationError("state must be a LorebuffaDialogueState")
        if state.node_id not in self._graph:
            raise ValidationError(
                "dialogue state references an unknown node",
                context={"node_id": state.node_id},
            )

    def _apply_effects(
        self, state: LorebuffaDialogueState, payload: Mapping[str, Any]
    ) -> None:
        trust = payload.get("trust_level")
        if trust is not None:
            state.trust_level = str(trust)
        quest = payload.get("quest_unlock")
        if quest:
            state.quests.add(str(quest))
        knowledge = payload.get("knowledge")
        if knowledge:
            state.knowledge.add(str(knowledge))
        faction = payload.get("faction_discover")
        if faction:
            state.factions.add(str(faction))

    def _apply_node_rewards(
        self, state: LorebuffaDialogueState, node_id: str
    ) -> None:
        if node_id in state.claimed_rewards:
            return
        rewards = self._graph[node_id].get("rewards")
        if not isinstance(rewards, Mapping):
            return

        rep = rewards.get("rep", 0)
        if isinstance(rep, int) and not isinstance(rep, bool):
            state.reputation += rep
        self._apply_effects(state, rewards)

        scoped_reputation = rewards.get("reputation")
        if isinstance(scoped_reputation, Mapping):
            for key, value in sorted(scoped_reputation.items()):
                state.knowledge.add(f"reputation:{key}:{value}")

        item = rewards.get("item")
        if item:
            state.inventory.add(str(item))
        state.claimed_rewards.add(node_id)


__all__ = [
    "LorebuffaDialogueRuntime",
    "LorebuffaDialogueState",
    "LorebuffaDialogueTurn",
    "completed_marina_dialogue",
]
