"""Deterministic NPC intent scoring from needs, personality and observed events."""
from dataclasses import dataclass
from ..contracts.errors import ContractError

@dataclass(frozen=True)
class Actor:
    id: str
    goals: dict[str, int]
    faction: str
    patience: int

def choose_intent(actor: Actor, signals: dict[str, int], *, seed: int=0) -> dict:
    if not isinstance(signals, dict) or len(signals) > 64 or type(seed) is not int:
        raise ContractError('invalid observation signal')
    if not actor.goals or any((type(v) is not int or not -100 <= v <= 100 for v in actor.goals.values())):
        raise ContractError('actor goals invalid')
    ordered = []
    for goal, weight in actor.goals.items():
        observed = signals.get(goal, 0)
        if type(observed) is not int or not -100 <= observed <= 100:
            raise ContractError('observation out of bounds')
        ordered.append((-(weight + observed), goal))
    ordered.sort()
    return {'actor': actor.id, 'intent': ordered[0][1], 'score': -ordered[0][0], 'evidence': 'bounded-signal-heuristic-not-inference'}
