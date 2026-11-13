"""DAG quest admission with resource prerequisites and deterministic completion."""
from dataclasses import dataclass
from ..contracts.graph import topological
from ..contracts.errors import ContractError
from ..contracts.identity import identifier

@dataclass(frozen=True)
class Quest:
    id: str
    needs: tuple[str, ...]
    requires: tuple[str, ...]
    rewards: tuple[str, ...]

def compile_quests(quests: list[Quest]) -> list[Quest]:
    if not isinstance(quests, list) or len(quests) > 5000:
        raise ContractError('invalid quest volume')
    by_id = {q.id: q for q in quests}
    if len(by_id) != len(quests):
        raise ContractError('duplicate quest ID')
    for q in quests:
        identifier(q.id)
        for item in q.needs + q.requires + q.rewards:
            identifier(item)
    order = topological({q.id: list(q.needs) for q in quests})
    return [by_id[id] for id in order]

def available(quests: list[Quest], completed: set[str], flags: set[str]) -> list[str]:
    return [q.id for q in compile_quests(quests) if q.id not in completed and set(q.needs).issubset(completed) and set(q.requires).issubset(flags)]
