"""Immutable game-state envelopes, input predicates and pure transition semantics."""
from dataclasses import dataclass
from .errors import ConflictError, ContractError
from .spec import Choice, World

@dataclass(frozen=True)
class GameState:
    world: str
    scene: str
    flags: frozenset[str]
    moves: int
    ended: bool
    revision: int

    def as_data(self) -> dict:
        return {'world': self.world, 'scene': self.scene, 'flags': sorted(self.flags), 'moves': self.moves, 'ended': self.ended, 'revision': self.revision}

def initial(world: World) -> GameState:
    return GameState(world.id, world.start, frozenset(), 0, world.start in world.endings, 0)

def allowed(state: GameState, choice: Choice) -> bool:
    return set(choice.requires).issubset(state.flags) and set(choice.costs).issubset(state.flags)

def advance(world: World, state: GameState, choice_id: str, *, expected_revision: int | None=None) -> GameState:
    if expected_revision is not None and expected_revision != state.revision:
        raise ConflictError('stale state revision')
    if state.world != world.id or state.scene not in world.scenes or state.ended:
        raise ContractError('state is foreign, invalid or terminal')
    matches = [c for c in world.scenes[state.scene].choices if c.id == choice_id]
    if len(matches) != 1 or not allowed(state, matches[0]):
        raise ContractError('choice unavailable or preconditions unmet')
    c = matches[0]
    new_flags = state.flags - set(c.costs) | set(c.grants)
    return GameState(world.id, c.destination, frozenset(new_flags), state.moves + 1, c.destination in world.endings, state.revision + 1)
