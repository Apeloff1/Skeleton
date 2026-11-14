"""Reject executable mapping subclasses from linearizable Mongo epoch reads."""
from __future__ import annotations

import unittest

from skeleton.persistence.mongo_source_epoch import MongoCanonicalSourceEpoch, MongoSourceEpochError


class _HostileDocument(dict):
    def get(self, key, default=None):
        raise AssertionError("untrusted mapping subclass executed")


class _Reader:
    def __init__(self, document):
        self.document = document
        self.calls = 0

    async def find_one(self, query, *, max_time_ms):
        self.calls += 1
        assert max_time_ms > 0
        return self.document


class MongoEpochDocumentShapeTests(unittest.IsolatedAsyncioTestCase):
    async def _read(self, document):
        witness = object.__new__(MongoCanonicalSourceEpoch)
        witness._reader = _Reader(document)
        return await witness.read_epoch(
            tenant_id="tenant", actor_id="actor", context_id="context",
        )

    async def test_hostile_mapping_subclass_never_executes(self):
        with self.assertRaisesRegex(MongoSourceEpochError, "quarantined"):
            await self._read(_HostileDocument(
                phase="stable", writer_token=None, epoch=2,
            ))

    async def test_exact_stable_document_is_readable(self):
        self.assertEqual(await self._read(
            {"phase": "stable", "writer_token": None, "epoch": 2},
        ), 2)

    async def test_stable_document_rejects_executable_phase_and_epoch(self):
        class ExecutableInt(int):
            def __eq__(self, other):
                raise AssertionError("untrusted epoch comparison executed")

        class ExecutableString(str):
            def __eq__(self, other):
                raise AssertionError("untrusted phase comparison executed")

        for doc in (
            {"phase": ExecutableString("stable"), "writer_token": None, "epoch": 2},
            {"phase": "stable", "writer_token": None, "epoch": ExecutableInt(2)},
        ):
            with self.subTest(document=repr(doc)):
                with self.assertRaises(MongoSourceEpochError):
                    await self._read(doc)

    async def test_noncanonical_phase_and_epoch_fail_closed(self):
        for document in (
            {"phase": "stable", "writer_token": None, "epoch": True},
            {"phase": "stable", "writer_token": None, "epoch": 3},
            {"phase": "writing", "writer_token": None, "epoch": 4},
            {"phase": "revoked", "writer_token": None, "epoch": 4},
            {"phase": "stable", "writer_token": "active", "epoch": 4},
            None,
        ):
            with self.subTest(document=repr(document)):
                with self.assertRaises(MongoSourceEpochError):
                    await self._read(document)
