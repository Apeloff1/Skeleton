"""Explicit branching by deterministic replay; no mutation of original session."""
from ..contracts.errors import ContractError
from ..persistence.game_store import GameStore

def fork(store: GameStore, source: str, destination: str, *, upto_revision: int) -> GameStore:
    if source == destination or type(upto_revision) is not int or upto_revision < 0:
        raise ContractError('invalid branch')
    records = store.journal.replay(source)
    if upto_revision > len(records):
        raise ContractError('branch point beyond source history')
    if store.journal.head(destination)[0] != 0:
        raise ContractError('destination already has history')
    for event in records[:upto_revision]:
        store.journal.append(destination, event['token'], event['kind'], event['body'], expected_revision=event['revision'] - 1)
    return GameStore(store.journal, store.world)
