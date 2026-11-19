"""Knowledge admission: no approved source, no processing or principal side effects.

These source-only tests qualify the negative-first canonical ingest boundary,
not live database migration, search relevance or original-content rights.
"""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.context.knowledge_plane.contracts import (
    KnowledgeError, KnowledgePolicy,
)
from skeleton.ai.runtime.operational_ai.context.knowledge_plane.ingest import (
    forget, ingest,
)


class ForbiddenConnection:
    def __init__(self):
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("invalid source reached protected SQLite")


class ForbiddenIdentity:
    def key(self):
        raise AssertionError("invalid source reached private principal")


def request(**changes):
    attrs = {
        "doc_id": "operator_notes",
        "title": "Original operator notes",
        "rights": "operator-authored",
        "kind": "text/plain",
        "approved": True,
        "expected_revision": 0,
        "policy": KnowledgePolicy(),
    }
    attrs.update(changes)
    return attrs


class KnowledgeQuarantineRestorationTests(unittest.TestCase):
    def test_unapproved_source_fails_before_any_database_or_identity(self):
        conn = ForbiddenConnection()
        for approval in (None, False, 1, "approved"):
            with self.subTest(value=approval), self.assertRaises(KnowledgeError):
                ingest(conn, ForbiddenIdentity(), b"safe text",
                       **request(approved=approval))
            self.assertEqual(conn.calls, [])

    def test_rights_and_content_type_are_not_synthetic_defaults(self):
        conn = ForbiddenConnection()
        for override in (
            {"rights": "unreviewed-web"},
            {"rights": ""},
            {"rights": None},
            {"kind": "application/octet-stream"},
            {"kind": "text/html"},
            {"kind": ""},
            {"doc_id": ""},
            {"doc_id": "not/relative"},
            {"title": ""},
            {"title": "bad\x00title"},
            {"expected_revision": -1},
            {"expected_revision": True},
            {"expected_revision": "0"},
        ):
            with self.subTest(override=override):
                with self.assertRaises(KnowledgeError):
                    ingest(conn, ForbiddenIdentity(), b"safe text",
                           **request(**override))
                self.assertEqual(conn.calls, [])

    def test_empty_nonbytes_and_budget_excess_fail_before_decode(self):
        conn = ForbiddenConnection()
        policy = KnowledgePolicy(max_document_bytes=1024)
        for payload in (b"", "", None, bytearray(b"no"), b"a" * 1025):
            with self.subTest(type=type(payload).__name__, size=len(payload) if payload is not None else 0):
                with self.assertRaises(KnowledgeError):
                    ingest(conn, ForbiddenIdentity(), payload,
                           **request(policy=policy))
                self.assertEqual(conn.calls, [])

    def test_deletion_requires_independent_approval_and_exact_revision(self):
        conn = ForbiddenConnection()
        for approved in (False, None, "yes", True):
            revisions = (0, True, -1, "1") if approved is True else (1,)
            for revision in revisions:
                with self.subTest(approved=approved,revision=revision):
                    with self.assertRaises(KnowledgeError):
                        forget(conn, ForbiddenIdentity(), doc_id="operator_notes",
                               approved=approved, expected_revision=revision)
                    self.assertEqual(conn.calls, [])

    def test_policy_does_not_accept_open_ended_archive_budgets(self):
        for attrs in (
            {"max_document_bytes": 0},
            {"max_total_bytes": 0},
            {"max_documents": 0},
            {"max_chunks": 0},
            {"chunk_characters": 0},
            {"chunk_overlap": 500},
            {"max_revisions": 100000},
            {"max_scan_rows": True},
        ):
            with self.subTest(attrs=attrs), self.assertRaises(KnowledgeError):
                KnowledgePolicy(**attrs)


if __name__ == "__main__":
    unittest.main()
