from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from skeleton.jeeves.agent.context_repository import (
    ContextEntry,
    ContextKind,
    ContextNamespace,
    ContextPatch,
    ContextPatchItem,
    ContextPolicyViolation,
    ContextRepository,
    PatchOperation,
)
from skeleton.jeeves.agent.memory import (
    InMemoryStore,
    MemoryError,
    MemoryNamespace,
    MemoryRecord,
)
from skeleton.jeeves.agent.types import MemoryKind
from skeleton.persistence.privacy_deletion import (
    DELETED,
    MATERIALIZED_SUMMARY,
    SEMANTIC_MEMORY,
    SQLitePrivacyDeletionAuthority,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class JeevesPrivacyDeletionIntegrationTests(unittest.TestCase):
    def test_authority_tombstone_scrubs_context_and_memory_and_fences_revival(self) -> None:
        authority = SQLitePrivacyDeletionAuthority()
        authority.register_copy(
            tenant_id="tenant",
            subject_id="user",
            copy_id="memory-copy",
            target_class=SEMANTIC_MEMORY,
            store_id="jeeves-memory",
            resource_ref="tenant/user/memory",
            content_digest=digest("remember me"),
        )
        authority.register_copy(
            tenant_id="tenant",
            subject_id="user",
            copy_id="context-copy",
            target_class=MATERIALIZED_SUMMARY,
            store_id="jeeves-context",
            resource_ref="tenant/user/context",
            content_digest=digest("context secret"),
        )

        memory = InMemoryStore()
        memory.put(
            MemoryRecord(
                memory_id="memory-one",
                namespace=MemoryNamespace(
                    "tenant", "user", "workspace-a", "session-a"
                ),
                kind=MemoryKind.EPISODIC,
                content="remember me",
                created_at=1.0,
                updated_at=1.0,
                metadata={"private_note": "must disappear"},
            )
        )
        memory.put(
            MemoryRecord(
                memory_id="memory-two",
                namespace=MemoryNamespace(
                    "tenant", "user", "workspace-b", "session-b"
                ),
                kind=MemoryKind.PREFERENCE,
                content="another secret",
                created_at=1.0,
                updated_at=1.0,
            )
        )
        memory.put(
            MemoryRecord(
                memory_id="other-user",
                namespace=MemoryNamespace(
                    "tenant", "other", "workspace-a", "session-a"
                ),
                kind=MemoryKind.EPISODIC,
                content="keep this",
                created_at=1.0,
                updated_at=1.0,
            )
        )

        namespace = ContextNamespace("tenant", "user", "workspace-a")
        context = ContextRepository(namespace, clock=lambda: 10.0)
        entry = ContextEntry(
            entry_id="entry-one",
            namespace=namespace,
            key="private-profile-key",
            kind=ContextKind.USER,
            content="context secret",
            created_at=1.0,
            updated_at=1.0,
            metadata={"private_note": "must disappear"},
        )
        patch = ContextPatch(
            patch_id="patch-one",
            namespace=namespace,
            items=(
                ContextPatchItem(
                    operation=PatchOperation.UPSERT,
                    key=entry.key,
                    entry=entry,
                    reason="store private profile",
                ),
            ),
            author="user-writer",
            created_at=1.0,
            rationale="contains private rationale",
            metadata={"private_note": "must disappear"},
        )
        commit = context.commit(
            "main",
            patch,
            message="contains private commit message",
            expected_head=None,
        )

        tombstone = authority.request_deletion(
            tenant_id="tenant",
            subject_id="user",
            deletion_id="delete-user",
            request_digest=digest("request"),
            reason_digest=digest("privacy request"),
        )
        receipt = tombstone.tombstone_digest

        deleted_memory_ids = memory.privacy_delete_subject(
            "tenant",
            "user",
            authority_receipt_digest=receipt,
        )
        self.assertEqual(
            deleted_memory_ids,
            ("memory-one", "memory-two"),
        )
        self.assertIsNone(memory.get("memory-one"))
        self.assertIsNone(memory.get("memory-two"))
        self.assertIsNotNone(memory.get("other-user"))
        self.assertEqual(
            memory.privacy_tombstone_receipt("tenant", "user"),
            receipt,
        )

        context.privacy_delete_all(authority_receipt_digest=receipt)
        scrubbed = context.snapshot_at(commit.commit_id)
        self.assertEqual(len(scrubbed.entries), 1)
        scrubbed_entry = scrubbed.entries[0]
        self.assertTrue(scrubbed_entry.tombstoned)
        self.assertEqual(scrubbed_entry.content, "")
        self.assertEqual(scrubbed_entry.evidence, ())
        self.assertEqual(scrubbed_entry.tags, ("privacy-tombstone",))
        self.assertNotEqual(scrubbed_entry.key, "private-profile-key")
        self.assertNotEqual(scrubbed_entry.entry_id, "entry-one")
        redacted_commit = context.commit_by_id(commit.commit_id)
        self.assertEqual(redacted_commit.author, "privacy-redacted")
        self.assertEqual(redacted_commit.message, "privacy-redacted")
        self.assertEqual(context.privacy_deletion_receipt(), receipt)

        authority.acknowledge_resolution(
            tenant_id="tenant",
            subject_id="user",
            copy_id="memory-copy",
            resolution=DELETED,
            receipt_digest=digest("|".join(deleted_memory_ids)),
        )
        authority.acknowledge_resolution(
            tenant_id="tenant",
            subject_id="user",
            copy_id="context-copy",
            resolution=DELETED,
            receipt_digest=digest(receipt + ":context"),
        )
        self.assertEqual(
            authority.pending_copies(
                tenant_id="tenant", subject_id="user"
            ),
            (),
        )

        with self.assertRaises(MemoryError):
            memory.put(
                MemoryRecord(
                    memory_id="memory-revival",
                    namespace=MemoryNamespace("tenant", "user"),
                    kind=MemoryKind.EPISODIC,
                    content="resurrected",
                    created_at=2.0,
                    updated_at=2.0,
                )
            )

        new_entry = ContextEntry(
            entry_id="entry-two",
            namespace=namespace,
            key="new-private-key",
            kind=ContextKind.USER,
            content="resurrected context",
            created_at=2.0,
            updated_at=2.0,
        )
        new_patch = ContextPatch(
            patch_id="patch-two",
            namespace=namespace,
            items=(
                ContextPatchItem(
                    operation=PatchOperation.UPSERT,
                    key=new_entry.key,
                    entry=new_entry,
                ),
            ),
            author="writer",
            created_at=2.0,
        )
        with self.assertRaises(ContextPolicyViolation):
            context.commit(
                "main",
                new_patch,
                message="revive",
                expected_head=context.head(),
            )

    def test_privacy_delete_is_idempotent_but_receipt_identity_is_fenced(self) -> None:
        memory = InMemoryStore()
        receipt = digest("receipt")
        self.assertEqual(
            memory.privacy_delete_subject(
                "tenant", "user", authority_receipt_digest=receipt
            ),
            (),
        )
        self.assertEqual(
            memory.privacy_delete_subject(
                "tenant", "user", authority_receipt_digest=receipt
            ),
            (),
        )
        with self.assertRaises(MemoryError):
            memory.privacy_delete_subject(
                "tenant",
                "user",
                authority_receipt_digest=digest("different"),
            )

        context = ContextRepository(
            ContextNamespace("tenant", "user"),
            clock=lambda: 1.0,
        )
        self.assertEqual(
            context.privacy_delete_all(
                authority_receipt_digest=receipt
            ),
            receipt,
        )
        self.assertEqual(
            context.privacy_delete_all(
                authority_receipt_digest=receipt
            ),
            receipt,
        )

    def test_canonical_and_ai_jeeves_privacy_surfaces_remain_identical(self) -> None:
        root = Path(__file__).resolve().parents[2]
        pairs = (
            (
                root / "skeleton/jeeves/agent/memory.py",
                root / "skeleton/ai/agents/jeeves/agent/memory.py",
            ),
            (
                root / "skeleton/jeeves/agent/context_repository.py",
                root / "skeleton/ai/agents/jeeves/agent/context_repository.py",
            ),
        )
        for canonical, mirror in pairs:
            self.assertEqual(canonical.read_bytes(), mirror.read_bytes())


if __name__ == "__main__":
    unittest.main()
