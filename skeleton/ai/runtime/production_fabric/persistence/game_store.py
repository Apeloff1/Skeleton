"""Crash-safe game-state replay: only journaled choices mutate authoritative state."""
from ..contracts.state import initial, advance, GameState
from ..contracts.spec import World
from ..contracts.errors import IntegrityError, ConflictError
from .journal import Journal

class GameStore:

    def __init__(self, journal: Journal, world: World):
        self.journal = journal
        self.world = world

    def load(self, stream: str) -> GameState:
        state = initial(self.world)
        for record in self.journal.replay(stream):
            if record['kind'] != 'choice':
                raise IntegrityError('unknown game event type')
            body = record['body']
            if set(body) != {'world', 'choice', 'before', 'after'} or body['world'] != self.world.id or body['before'] != state.as_data():
                raise IntegrityError('game event state mismatch')
            try:
                state = advance(self.world, state, body['choice'])
            except Exception as exc:
                raise IntegrityError('replayed choice invalid') from exc
            if body['after'] != state.as_data():
                raise IntegrityError('game event poststate mismatch')
        return state

    def choose(self, stream: str, token: str, choice: str, *, expected_revision: int) -> tuple[GameState, dict]:
        current = self.load(stream)
        if expected_revision != current.revision:
            entry = self.journal.db.execute('SELECT body FROM events WHERE stream=? AND token=?', (stream, token)).fetchone()
            if entry is None:
                raise ConflictError('stale choice revision')
            import json
            raw = json.loads(entry[0])
            state = self.load(stream)
            if raw.get('choice') != choice:
                raise ConflictError('idempotency token reused')
            return (state, {'duplicate': True, 'revision': raw['after']['revision']})
        next_state = advance(self.world, current, choice, expected_revision=expected_revision)
        body = {'world': self.world.id, 'choice': choice, 'before': current.as_data(), 'after': next_state.as_data()}
        receipt = self.journal.append(stream, token, 'choice', body, expected_revision=expected_revision)
        return (self.load(stream), receipt)
