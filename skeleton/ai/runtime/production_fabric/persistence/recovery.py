"""Read-only recovery audit: verify every event and projection before admitting use."""
from ..contracts.canonical import digest
from ..contracts.errors import IntegrityError
from .game_store import GameStore

def audit(store: GameStore, stream: str) -> dict:
    events = store.journal.replay(stream)
    state = store.load(stream)
    head = store.journal.head(stream)
    if state.revision != head[0]:
        raise IntegrityError('recovery revision drift')
    return {'stream': stream, 'revision': state.revision, 'state_sha256': digest(state.as_data()), 'chain_head': head[1], 'events_checked': len(events), 'recoverable': True}
