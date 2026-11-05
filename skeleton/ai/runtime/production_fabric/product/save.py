"""Save receipt is a replayable position, never an alternate authoritative truth."""
from ..contracts.canonical import digest
from ..contracts.errors import IntegrityError
from ..persistence.game_store import GameStore

def save(store: GameStore, stream: str) -> dict:
    state = store.load(stream)
    return {'schema_version': 1, 'stream': stream, 'state': state.as_data(), 'state_sha256': digest(state.as_data()), 'chain': store.journal.head(stream)[1]}

def validate(store: GameStore, receipt: dict) -> bool:
    expected = save(store, receipt.get('stream', ''))
    if expected != receipt:
        raise IntegrityError('save receipt is stale or corrupt')
    return True
