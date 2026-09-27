from __future__ import annotations

import pytest

from skeleton.frontier.operation_stream import StreamContractError
from skeleton.frontier.operation_stream_store_mongo import (
    MongoOperationEventStore,
)


class _Transaction:
    def __init__(self, session) -> None:
        self.session = session

    def __enter__(self):
        self.session.in_transaction = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.session.in_transaction = False


class _Session:
    def __init__(self, *, supported: bool) -> None:
        self.supported = supported
        self.in_transaction = False
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.in_transaction = False

    def start_transaction(self):
        return _Transaction(self)


class _Client:
    def __init__(self, *, supported: bool) -> None:
        self.supported = supported
        self.sessions: list[_Session] = []

    def start_session(self):
        session = _Session(supported=self.supported)
        self.sessions.append(session)
        return session


class _Collection:
    def __init__(self, database) -> None:
        self.database = database
        self.indexes = []

    def create_index(self, *args, **kwargs):
        self.indexes.append((args, kwargs))
        return kwargs.get("name")

    def find_one(self, query, projection=None, *, session=None):
        del query, projection
        if session is None or not session.in_transaction:
            raise AssertionError("capability probe must execute in a transaction")
        session.reads += 1
        if not session.supported:
            raise RuntimeError("Transaction numbers are only allowed on a replica set member")
        return None


class _Database:
    def __init__(self, *, supported: bool) -> None:
        self.client = _Client(supported=supported)
        self._collections = {}

    def __getitem__(self, name: str):
        return self._collections.setdefault(name, _Collection(self))


def test_mongo_stream_transaction_preflight_executes_real_transactional_read() -> None:
    database = _Database(supported=True)
    store = MongoOperationEventStore(database)

    store.validate_transaction_capability()

    assert len(database.client.sessions) == 1
    assert database.client.sessions[0].reads == 1
    assert database.client.sessions[0].in_transaction is False


def test_mongo_stream_transaction_preflight_rejects_standalone_topology() -> None:
    database = _Database(supported=False)
    store = MongoOperationEventStore(database)

    with pytest.raises(
        StreamContractError,
        match="transaction-capable deployment",
    ):
        store.validate_transaction_capability()


def test_mongo_stream_transaction_preflight_rejects_client_without_sessions() -> None:
    database = _Database(supported=True)
    database.client = object()
    store = MongoOperationEventStore(database)

    with pytest.raises(
        StreamContractError,
        match="transaction-capable deployment",
    ):
        store.validate_transaction_capability()
