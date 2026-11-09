from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.model_rollback import (
    DataCursorIdentity,
    MigrationEdge,
    ModelCheckpoint,
    ModelRollbackError,
    OptimizerStateIdentity,
    RollbackPolicy,
    RollbackReceipt,
    RuntimeStateEnvelope,
    build_checkpoint,
    evaluate_rollback,
    evaluate_rollback_evidence,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LearningRollbackEvidenceTests(unittest.TestCase):
    def optimizer(self, *, schema: str = "opt-v1") -> OptimizerStateIdentity:
        return OptimizerStateIdentity(
            optimizer_family="adamw",
            optimizer_version="2.0",
            schema_version=schema,
            parameter_group_digest=_sha("groups"),
            state_digest=_sha("optimizer-state"),
        )

    def cursor(self, *, schema: str = "cursor-v1") -> DataCursorIdentity:
        return DataCursorIdentity(
            data_manifest_root=_sha("data"),
            mixture_digest=_sha("mixture"),
            cursor_schema=schema,
            draw_index=100,
            cursor_digest=_sha("cursor"),
        )

    def checkpoint(
        self,
        *,
        optimizer_schema: str = "opt-v1",
        cursor_schema: str = "cursor-v1",
    ):
        return build_checkpoint(
            checkpoint_id="checkpoint-100",
            model_artifact_digest=_sha("model"),
            architecture_config_digest=_sha("arch"),
            representation_id="rep:" + _sha("rep"),
            runtime_abi="skeleton.runtime.v1",
            optimizer=self.optimizer(schema=optimizer_schema),
            data_cursor=self.cursor(schema=cursor_schema),
            training_step=100,
            checkpoint_format="skeleton-checkpoint",
            checkpoint_format_version="1",
            code_revision="abc123",
            rng_state_digest=_sha("rng"),
        )

    def runtime(
        self,
        *,
        optimizer_schema: str = "opt-v1",
        cursor_schema: str = "cursor-v1",
        floor: int = 50,
    ) -> RuntimeStateEnvelope:
        return RuntimeStateEnvelope(
            architecture_config_digest=_sha("arch"),
            representation_id="rep:" + _sha("rep"),
            runtime_abi="skeleton.runtime.v1",
            optimizer_family="adamw",
            optimizer_version="2.0",
            optimizer_schema_version=optimizer_schema,
            parameter_group_digest=_sha("groups"),
            data_manifest_root=_sha("data"),
            mixture_digest=_sha("mixture"),
            cursor_schema=cursor_schema,
            checkpoint_format="skeleton-checkpoint",
            supported_checkpoint_versions=("1",),
            minimum_training_step=floor,
        )

    def test_decision_evidence_binds_checkpoint_runtime_policy_and_inventory(self) -> None:
        checkpoint = self.checkpoint()
        runtime = self.runtime()
        policy = RollbackPolicy()
        evidence = evaluate_rollback_evidence(
            checkpoint,
            runtime,
            policy=policy,
        )

        self.assertTrue(evidence.receipt.admissible)
        self.assertEqual(
            evidence.checkpoint_claimed_integrity_digest,
            checkpoint.integrity_digest,
        )
        self.assertEqual(
            evidence.checkpoint_computed_integrity_digest,
            checkpoint.computed_integrity_digest,
        )
        self.assertEqual(evidence.runtime_digest, runtime.digest)
        self.assertEqual(evidence.policy_digest, policy.digest)
        self.assertEqual(evidence.migration_inventory_digests, ())
        self.assertEqual(evidence.digest, evaluate_rollback_evidence(
            checkpoint,
            runtime,
            policy=policy,
        ).digest)

    def test_runtime_or_policy_change_changes_decision_evidence_identity(self) -> None:
        checkpoint = self.checkpoint()
        base = evaluate_rollback_evidence(checkpoint, self.runtime(floor=50))
        changed_runtime = evaluate_rollback_evidence(
            checkpoint,
            self.runtime(floor=99),
        )
        changed_policy = evaluate_rollback_evidence(
            checkpoint,
            self.runtime(floor=50),
            policy=RollbackPolicy(forbid_step_regression_below=90),
        )

        self.assertNotEqual(base.runtime_digest, changed_runtime.runtime_digest)
        self.assertNotEqual(base.digest, changed_runtime.digest)
        self.assertNotEqual(base.policy_digest, changed_policy.policy_digest)
        self.assertNotEqual(base.digest, changed_policy.digest)

    def test_tampered_checkpoint_evidence_preserves_claimed_and_computed_identity(self) -> None:
        checkpoint = self.checkpoint()
        tampered = ModelCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            model_artifact_digest=_sha("tampered-model"),
            architecture_config_digest=checkpoint.architecture_config_digest,
            representation_id=checkpoint.representation_id,
            runtime_abi=checkpoint.runtime_abi,
            optimizer=checkpoint.optimizer,
            data_cursor=checkpoint.data_cursor,
            training_step=checkpoint.training_step,
            checkpoint_format=checkpoint.checkpoint_format,
            checkpoint_format_version=checkpoint.checkpoint_format_version,
            code_revision=checkpoint.code_revision,
            rng_state_digest=checkpoint.rng_state_digest,
            integrity_digest=checkpoint.integrity_digest,
            parent_checkpoint_id=checkpoint.parent_checkpoint_id,
            metadata=checkpoint.metadata,
        )
        evidence = evaluate_rollback_evidence(tampered, self.runtime())

        self.assertFalse(evidence.receipt.admissible)
        self.assertIn(
            "checkpoint integrity digest mismatch",
            evidence.receipt.blockers,
        )
        self.assertNotEqual(
            evidence.checkpoint_claimed_integrity_digest,
            evidence.checkpoint_computed_integrity_digest,
        )

    def test_duplicate_migration_ids_fail_closed(self) -> None:
        first = MigrationEdge(
            component="optimizer",
            from_version="opt-v0",
            to_version="opt-v1",
            migration_id="migration:shared",
            reversible=True,
            verifier_ref="verify:optimizer",
        )
        second = MigrationEdge(
            component="data_cursor",
            from_version="cursor-v0",
            to_version="cursor-v1",
            migration_id="migration:shared",
            reversible=True,
            verifier_ref="verify:cursor",
        )
        with self.assertRaisesRegex(ModelRollbackError, "migration ids must be unique"):
            evaluate_rollback(
                self.checkpoint(),
                self.runtime(),
                migrations=(first, second),
            )

    def test_unsupported_migration_component_is_not_silently_ignored(self) -> None:
        edge = MigrationEdge(
            component="weights",
            from_version="v0",
            to_version="v1",
            migration_id="migration:weights",
            reversible=True,
            verifier_ref="verify:weights",
        )
        with self.assertRaisesRegex(ModelRollbackError, "unsupported migration component"):
            evaluate_rollback(
                self.checkpoint(),
                self.runtime(),
                migrations=(edge,),
            )

    def test_migration_inventory_identity_is_order_independent(self) -> None:
        optimizer = MigrationEdge(
            component="optimizer",
            from_version="opt-v0",
            to_version="opt-v1",
            migration_id="migration:optimizer",
            reversible=True,
            verifier_ref="verify:optimizer",
        )
        cursor = MigrationEdge(
            component="data_cursor",
            from_version="cursor-v0",
            to_version="cursor-v1",
            migration_id="migration:cursor",
            reversible=True,
            verifier_ref="verify:cursor",
        )
        checkpoint = self.checkpoint(
            optimizer_schema="opt-v0",
            cursor_schema="cursor-v0",
        )
        runtime = self.runtime()
        policy = RollbackPolicy(
            allow_optimizer_migration=True,
            allow_cursor_migration=True,
        )
        forward = evaluate_rollback_evidence(
            checkpoint,
            runtime,
            policy=policy,
            migrations=(optimizer, cursor),
        )
        reverse = evaluate_rollback_evidence(
            checkpoint,
            runtime,
            policy=policy,
            migrations=(cursor, optimizer),
        )

        self.assertTrue(forward.receipt.admissible)
        self.assertEqual(
            forward.migration_inventory_digests,
            reverse.migration_inventory_digests,
        )
        self.assertEqual(forward.digest, reverse.digest)

    def test_rollback_receipt_rejects_incoherent_admission_state(self) -> None:
        with self.assertRaisesRegex(
            ModelRollbackError,
            "admissible rollback cannot contain blockers",
        ):
            RollbackReceipt(
                checkpoint_id="checkpoint",
                admissible=True,
                blockers=("mismatch",),
                migration_ids=(),
            )
        with self.assertRaisesRegex(
            ModelRollbackError,
            "inadmissible rollback must explain",
        ):
            RollbackReceipt(
                checkpoint_id="checkpoint",
                admissible=False,
                blockers=(),
                migration_ids=(),
            )


if __name__ == "__main__":
    unittest.main()
