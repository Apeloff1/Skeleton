from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.model_rollback import (
    DataCursorIdentity,
    MigrationEdge,
    ModelCheckpoint,
    OptimizerStateIdentity,
    RollbackPolicy,
    RuntimeStateEnvelope,
    build_checkpoint,
    evaluate_rollback,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ModelRollbackCompatibilityTests(unittest.TestCase):
    def optimizer(self, *, schema: str = "opt-state-v1") -> OptimizerStateIdentity:
        return OptimizerStateIdentity(
            optimizer_family="adamw",
            optimizer_version="2.0.0",
            schema_version=schema,
            parameter_group_digest=sha("parameter-groups"),
            state_digest=sha("optimizer-state"),
        )

    def cursor(self, *, schema: str = "cursor-v1") -> DataCursorIdentity:
        return DataCursorIdentity(
            data_manifest_root=sha("dataset-root"),
            mixture_digest=sha("mixture"),
            cursor_schema=schema,
            draw_index=800,
            cursor_digest=sha("cursor"),
        )

    def checkpoint(
        self,
        *,
        optimizer_schema: str = "opt-state-v1",
        cursor_schema: str = "cursor-v1",
        step: int = 800,
    ):
        return build_checkpoint(
            checkpoint_id=f"checkpoint-{step}",
            model_artifact_digest=sha("model"),
            architecture_config_digest=sha("arch"),
            representation_id="rep:" + sha("rep"),
            runtime_abi="skeleton.inference.v1",
            optimizer=self.optimizer(schema=optimizer_schema),
            data_cursor=self.cursor(schema=cursor_schema),
            training_step=step,
            checkpoint_format="skeleton-checkpoint",
            checkpoint_format_version="1",
            code_revision="deadbeef",
            rng_state_digest=sha("rng"),
        )

    def runtime(self) -> RuntimeStateEnvelope:
        return RuntimeStateEnvelope(
            architecture_config_digest=sha("arch"),
            representation_id="rep:" + sha("rep"),
            runtime_abi="skeleton.inference.v1",
            optimizer_family="adamw",
            optimizer_version="2.0.0",
            optimizer_schema_version="opt-state-v1",
            parameter_group_digest=sha("parameter-groups"),
            data_manifest_root=sha("dataset-root"),
            mixture_digest=sha("mixture"),
            cursor_schema="cursor-v1",
            checkpoint_format="skeleton-checkpoint",
            supported_checkpoint_versions=("1",),
            minimum_training_step=500,
        )

    def test_exact_compatible_checkpoint_is_admissible(self) -> None:
        checkpoint = self.checkpoint()
        receipt = evaluate_rollback(checkpoint, self.runtime())
        self.assertTrue(receipt.admissible, receipt.blockers)
        self.assertEqual(receipt.migration_ids, ())

    def test_representation_identity_mismatch_blocks_rollback(self) -> None:
        runtime = self.runtime()
        altered = RuntimeStateEnvelope(
            architecture_config_digest=runtime.architecture_config_digest,
            representation_id="rep:" + sha("different"),
            runtime_abi=runtime.runtime_abi,
            optimizer_family=runtime.optimizer_family,
            optimizer_version=runtime.optimizer_version,
            optimizer_schema_version=runtime.optimizer_schema_version,
            parameter_group_digest=runtime.parameter_group_digest,
            data_manifest_root=runtime.data_manifest_root,
            mixture_digest=runtime.mixture_digest,
            cursor_schema=runtime.cursor_schema,
            checkpoint_format=runtime.checkpoint_format,
            supported_checkpoint_versions=runtime.supported_checkpoint_versions,
            minimum_training_step=runtime.minimum_training_step,
        )
        receipt = evaluate_rollback(self.checkpoint(), altered)
        self.assertFalse(receipt.admissible)
        self.assertIn("representation identity is incompatible", receipt.blockers)

    def test_optimizer_parameter_group_mismatch_blocks_rollback(self) -> None:
        runtime = self.runtime()
        altered = RuntimeStateEnvelope(
            architecture_config_digest=runtime.architecture_config_digest,
            representation_id=runtime.representation_id,
            runtime_abi=runtime.runtime_abi,
            optimizer_family=runtime.optimizer_family,
            optimizer_version=runtime.optimizer_version,
            optimizer_schema_version=runtime.optimizer_schema_version,
            parameter_group_digest=sha("different-groups"),
            data_manifest_root=runtime.data_manifest_root,
            mixture_digest=runtime.mixture_digest,
            cursor_schema=runtime.cursor_schema,
            checkpoint_format=runtime.checkpoint_format,
            supported_checkpoint_versions=runtime.supported_checkpoint_versions,
            minimum_training_step=runtime.minimum_training_step,
        )
        receipt = evaluate_rollback(self.checkpoint(), altered)
        self.assertFalse(receipt.admissible)
        self.assertIn("optimizer parameter groups are incompatible", receipt.blockers)

    def test_schema_migration_is_forbidden_by_default(self) -> None:
        receipt = evaluate_rollback(
            self.checkpoint(optimizer_schema="opt-state-v0"),
            self.runtime(),
        )
        self.assertFalse(receipt.admissible)
        self.assertIn("optimizer schema requires forbidden migration", receipt.blockers)

    def test_explicit_reversible_optimizer_migration_can_be_admitted(self) -> None:
        edge = MigrationEdge(
            component="optimizer",
            from_version="opt-state-v0",
            to_version="opt-state-v1",
            migration_id="migration:optimizer:v0-v1",
            reversible=True,
            verifier_ref="test:optimizer-roundtrip",
        )
        receipt = evaluate_rollback(
            self.checkpoint(optimizer_schema="opt-state-v0"),
            self.runtime(),
            policy=RollbackPolicy(allow_optimizer_migration=True),
            migrations=(edge,),
        )
        self.assertTrue(receipt.admissible, receipt.blockers)
        self.assertEqual(receipt.migration_ids, ("migration:optimizer:v0-v1",))

    def test_irreversible_migration_is_rejected_when_reversibility_required(self) -> None:
        edge = MigrationEdge(
            component="optimizer",
            from_version="opt-state-v0",
            to_version="opt-state-v1",
            migration_id="migration:irreversible",
            reversible=False,
            verifier_ref="test:no-roundtrip",
        )
        receipt = evaluate_rollback(
            self.checkpoint(optimizer_schema="opt-state-v0"),
            self.runtime(),
            policy=RollbackPolicy(allow_optimizer_migration=True),
            migrations=(edge,),
        )
        self.assertFalse(receipt.admissible)
        self.assertIn("optimizer schema migration is unavailable", receipt.blockers)

    def test_data_mixture_drift_blocks_rollback(self) -> None:
        runtime = self.runtime()
        altered = RuntimeStateEnvelope(
            architecture_config_digest=runtime.architecture_config_digest,
            representation_id=runtime.representation_id,
            runtime_abi=runtime.runtime_abi,
            optimizer_family=runtime.optimizer_family,
            optimizer_version=runtime.optimizer_version,
            optimizer_schema_version=runtime.optimizer_schema_version,
            parameter_group_digest=runtime.parameter_group_digest,
            data_manifest_root=runtime.data_manifest_root,
            mixture_digest=sha("different-mixture"),
            cursor_schema=runtime.cursor_schema,
            checkpoint_format=runtime.checkpoint_format,
            supported_checkpoint_versions=runtime.supported_checkpoint_versions,
            minimum_training_step=runtime.minimum_training_step,
        )
        receipt = evaluate_rollback(self.checkpoint(), altered)
        self.assertFalse(receipt.admissible)
        self.assertIn("training mixture identity is incompatible", receipt.blockers)

    def test_rollback_floor_prevents_excessive_state_regression(self) -> None:
        receipt = evaluate_rollback(self.checkpoint(step=499), self.runtime())
        self.assertFalse(receipt.admissible)
        self.assertIn(
            "checkpoint training step violates rollback floor",
            receipt.blockers,
        )

    def test_checkpoint_integrity_tampering_blocks_rollback(self) -> None:
        checkpoint = self.checkpoint()
        tampered = ModelCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            model_artifact_digest=sha("tampered-model"),
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
        receipt = evaluate_rollback(tampered, self.runtime())
        self.assertFalse(receipt.admissible)
        self.assertIn("checkpoint integrity digest mismatch", receipt.blockers)

    def test_cursor_schema_requires_explicit_verified_migration(self) -> None:
        edge = MigrationEdge(
            component="data_cursor",
            from_version="cursor-v0",
            to_version="cursor-v1",
            migration_id="migration:cursor:v0-v1",
            reversible=True,
            verifier_ref="test:cursor-roundtrip",
        )
        blocked = evaluate_rollback(
            self.checkpoint(cursor_schema="cursor-v0"),
            self.runtime(),
        )
        self.assertFalse(blocked.admissible)

        allowed = evaluate_rollback(
            self.checkpoint(cursor_schema="cursor-v0"),
            self.runtime(),
            policy=RollbackPolicy(allow_cursor_migration=True),
            migrations=(edge,),
        )
        self.assertTrue(allowed.admissible, allowed.blockers)
        self.assertEqual(allowed.migration_ids, ("migration:cursor:v0-v1",))


if __name__ == "__main__":
    unittest.main()
