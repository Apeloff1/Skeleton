"""Adversarial majority recovery for authenticated native scheduler replicas."""
from __future__ import annotations

import json
import unittest

from skeleton.ai.model_runtime.admission_replicas import (
    MAX_REPLICA_BYTES, create_admission_replica, decode_admission_replica,
    recover_admission_quorum,
)
from skeleton.ai.model_runtime.admission_scheduler import (
    AdmissionLimits, RuntimeAdmissionScheduler,
)
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest, ModelRuntimeError
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler


KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))
MEMBERS = ("zone-a", "zone-b", "zone-c")


class TestReplicatedCheckpointRecovery(unittest.TestCase):
    def build(self):
        limits = AdmissionLimits(
            max_active_requests=2, max_queued_requests=4, max_batch_size=1,
            max_tokens_per_batch=50, kv_capacity_bytes=100, max_age_boost=10,
        )
        policy = RuntimePolicyCompiler().compile(2024)
        scheduler = RuntimeAdmissionScheduler(limits, policy=policy)
        scheduler.submit(BatchRequest("first", 1, 2), kv_bytes=15)
        scheduler.admit()
        scheduler.submit(BatchRequest("second", 2, 3), kv_bytes=20)
        return scheduler

    def replicas(self, scheduler=None, term=4, members=MEMBERS):
        scheduler = scheduler or self.build()
        return {
            member: create_admission_replica(
                scheduler, member_id=member, leader_term=term, secret_key=KEY
            )
            for member in members
        }

    def recover(self, copies, *, term=4, sequence=0, members=MEMBERS, **kw):
        return recover_admission_quorum(
            copies, members=members, secret_key=KEY, minimum_term=term,
            minimum_sequence=sequence, **kw,
        )

    def test_three_way_healthy_quorum_and_parity(self):
        scheduler = self.build()
        copies = self.replicas(scheduler)
        recovered = self.recover(
            copies, expected_policy=scheduler.policy,
            expected_limits=scheduler.limits,
        )
        self.assertEqual(recovered.supporters, MEMBERS)
        self.assertEqual(recovered.repair_targets, ())
        self.assertEqual(recovered.scheduler.snapshot(), scheduler.snapshot())
        self.assertEqual(recovered.sequence, scheduler.snapshot()["sequence"])

    def test_one_missing_replica_is_recoverable(self):
        copies = self.replicas()
        copies.pop("zone-b")
        recovered = self.recover(copies)
        self.assertEqual(recovered.supporters, ("zone-a", "zone-c"))
        self.assertEqual(recovered.missing_members, ("zone-b",))
        self.assertEqual(recovered.repair_targets, ("zone-b",))

    def test_one_corrupted_replica_is_recoverable(self):
        copies = self.replicas()
        copies["zone-c"] = copies["zone-c"][:-2] + b"zz"
        recovered = self.recover(copies)
        self.assertEqual(recovered.invalid_members, ("zone-c",))
        self.assertEqual(recovered.supporters, ("zone-a", "zone-b"))

    def test_one_replica_with_wrong_hmac_key_is_recoverable(self):
        copies = self.replicas()
        copies["zone-c"] = create_admission_replica(
            self.build(), member_id="zone-c", leader_term=4, secret_key=OTHER_KEY
        )
        recovered = self.recover(copies)
        self.assertEqual(recovered.invalid_members, ("zone-c",))

    def test_two_missing_or_corrupt_replicas_fail_closed(self):
        copies = self.replicas()
        for broken in (
            {"zone-a": copies["zone-a"]},
            {"zone-a": b"bad", "zone-b": b"bad", "zone-c": copies["zone-c"]},
        ):
            with self.subTest(broken=tuple(broken)), self.assertRaisesRegex(
                ModelRuntimeError, "quorum"
            ):
                self.recover(broken)

    def test_minority_divergence_does_not_override_majority(self):
        first = self.build()
        second = self.build()
        second.submit(BatchRequest("different", 1, 1), kv_bytes=10)
        # A minority different revision never substitutes for the quorum.
        same = self.replicas(first)
        rogue = create_admission_replica(
            second, member_id="zone-c", leader_term=4, secret_key=KEY
        )
        same["zone-c"] = rogue
        recovered = self.recover(same)
        self.assertEqual(recovered.supporters, ("zone-a", "zone-b"))

    def test_three_distinct_conflicting_revisions_fail_closed(self):
        base = self.build()
        copies = self.replicas(base)
        for member, suffix in zip(MEMBERS, ("x", "y", "z")):
            state = self.build()
            state.submit(BatchRequest(suffix, 1, 1), kv_bytes=1)
            copies[member] = create_admission_replica(
                state, member_id=member, leader_term=4, secret_key=KEY
            )
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(copies)

    def test_parent_revision_is_part_of_vote(self):
        base = self.build()
        copies = self.replicas(base)
        copies["zone-c"] = create_admission_replica(
            base, member_id="zone-c", leader_term=4, secret_key=KEY,
            parent_digest="a" * 64,
        )
        self.assertEqual(self.recover(copies).supporters, ("zone-a", "zone-b"))
        copies["zone-b"] = create_admission_replica(
            base, member_id="zone-b", leader_term=4, secret_key=KEY,
            parent_digest="b" * 64,
        )
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(copies)

    def test_uncommitted_single_newer_revision_never_wins(self):
        old = self.build()
        copies = self.replicas(old)
        old_sequence = old.snapshot()["sequence"]
        old.submit(BatchRequest("new", 1, 1), kv_bytes=1)
        copies["zone-c"] = create_admission_replica(
            old, member_id="zone-c", leader_term=5, secret_key=KEY
        )
        recovered = self.recover(copies)
        self.assertEqual(recovered.leader_term, 4)
        self.assertEqual(recovered.sequence, old_sequence)
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(copies, term=5)

    def test_sequence_fence_rejects_majority_rollback(self):
        scheduler = self.build()
        copies = self.replicas(scheduler)
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(copies, sequence=scheduler.snapshot()["sequence"] + 1)

    def test_expected_digest_pin_rejects_stale_quorum(self):
        copies = self.replicas()
        with self.assertRaisesRegex(ModelRuntimeError, "quorum"):
            self.recover(copies, expected_digest="0" * 64)

    def test_rebuild_damaged_replica_from_quorum_without_mutating_winner(self):
        copies = self.replicas()
        copies["zone-b"] = b"broken"
        result = self.recover(copies)
        before = result.scheduler.snapshot()
        repaired = result.rebuild_replica("zone-b", secret_key=KEY)
        self.assertEqual(result.scheduler.snapshot(), before)
        decoded = decode_admission_replica(
            repaired, member_id="zone-b", secret_key=KEY
        )
        self.assertEqual(decoded.scheduler.snapshot(), before)
        copies["zone-b"] = repaired
        self.assertEqual(self.recover(copies).supporters, MEMBERS)

    def test_repair_cannot_override_valid_supporter(self):
        result = self.recover(self.replicas())
        with self.assertRaisesRegex(ModelRuntimeError, "not eligible"):
            result.rebuild_replica("zone-a", secret_key=KEY)

    def test_repair_uses_original_snapshot_after_scheduler_mutation(self):
        copies = self.replicas()
        copies.pop("zone-c")
        result = self.recover(copies)
        original = result.scheduler.snapshot()
        result.scheduler.cancel("second")
        rebuilt = result.rebuild_replica("zone-c", secret_key=KEY)
        decoded = decode_admission_replica(
            rebuilt, member_id="zone-c", secret_key=KEY
        )
        self.assertEqual(decoded.scheduler.snapshot(), original)
        self.assertNotEqual(result.scheduler.snapshot(), original)

    def test_decode_wrong_member_binding_is_rejected(self):
        blob = self.replicas()["zone-a"]
        with self.assertRaisesRegex(ModelRuntimeError, "identity"):
            decode_admission_replica(blob, member_id="zone-b", secret_key=KEY)

    def test_decode_wrong_key_is_rejected(self):
        blob = self.replicas()["zone-a"]
        with self.assertRaisesRegex(ModelRuntimeError, "authentication"):
            decode_admission_replica(blob, member_id="zone-a", secret_key=OTHER_KEY)

    def test_invalid_canonical_envelope_rejected(self):
        blob = self.replicas()["zone-a"]
        for altered in (b" " + blob, blob + b" ", blob.replace(b'",', b'", ', 1)):
            with self.subTest(altered=altered[:20]), self.assertRaises(ModelRuntimeError):
                decode_admission_replica(altered, member_id="zone-a", secret_key=KEY)

    def test_duplicate_json_keys_are_rejected(self):
        blob = self.replicas()["zone-a"]
        bad = blob.replace(b'"schema":', b'"schema":"shadow","schema":', 1)
        with self.assertRaisesRegex(ModelRuntimeError, "duplicate JSON"):
            decode_admission_replica(bad, member_id="zone-a", secret_key=KEY)

    def test_invalid_authentication_before_snapshot_is_detected(self):
        blob = self.replicas()["zone-a"]
        obj = json.loads(blob)
        obj["snapshot"]["sequence"] += 1
        tampered = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaisesRegex(ModelRuntimeError, "authentication"):
            decode_admission_replica(tampered, member_id="zone-a", secret_key=KEY)

    def test_oversized_replica_payload_fails_without_json_parse(self):
        with self.assertRaisesRegex(ModelRuntimeError, "byte size"):
            decode_admission_replica(b"x" * (MAX_REPLICA_BYTES + 1), member_id="zone-a", secret_key=KEY)

    def test_two_member_configuration_is_not_an_authenticated_quorum(self):
        with self.assertRaisesRegex(ModelRuntimeError, "membership"):
            self.recover({}, members=("zone-a", "zone-b"))

    def test_unknown_or_duplicated_member_identity_rejected(self):
        with self.assertRaisesRegex(ModelRuntimeError, "membership"):
            self.recover({}, members=("zone-a", "zone-a", "zone-b"))
        with self.assertRaisesRegex(ModelRuntimeError, "member"):
            self.recover({"outsider": b"unexpected"})

    def test_boolean_or_negative_fencing_inputs_rejected(self):
        for term, sequence in ((True, 0), (-1, 0), (4, True), (4, -1)):
            with self.subTest(term=term, sequence=sequence), self.assertRaisesRegex(
                ModelRuntimeError, "invalid replica"
            ):
                self.recover({}, term=term, sequence=sequence)

    def test_missing_or_short_hmac_key_fails_closed(self):
        with self.assertRaisesRegex(ModelRuntimeError, "HMAC"):
            recover_admission_quorum({}, members=MEMBERS, secret_key=b"short", minimum_term=0, minimum_sequence=0)
        with self.assertRaisesRegex(ModelRuntimeError, "HMAC"):
            create_admission_replica(self.build(), member_id="zone-a", leader_term=0, secret_key=b"short")

    def test_five_member_quorum_recovers_from_two_failures(self):
        members = tuple(f"zone-{v}" for v in "abcde")
        copies = self.replicas(members=members)
        copies.pop("zone-d")
        copies.pop("zone-e")
        result = self.recover(copies, members=members)
        self.assertEqual(len(result.supporters), 3)
        self.assertEqual(result.repair_targets, ("zone-d", "zone-e"))

    def test_no_side_effects_from_recovery_replays(self):
        source = self.build()
        copies = self.replicas(source)
        first = self.recover(copies)
        second = self.recover(copies)
        self.assertEqual(first.scheduler.snapshot(), second.scheduler.snapshot())
        self.assertEqual(first.supporters, second.supporters)
        self.assertEqual(source.snapshot(), first.scheduler.snapshot())


if __name__ == "__main__":
    unittest.main()
