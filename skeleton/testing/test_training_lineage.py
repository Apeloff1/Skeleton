from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.training_lineage import (
    DatasetShardManifest,
    MixtureComponent,
    MixtureManifest,
    SourceRecord,
    TrainingDataManifest,
    TrainingLineageError,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TrainingLineageTests(unittest.TestCase):
    def manifest(self) -> TrainingDataManifest:
        sources = (
            SourceRecord(
                source_id="source:a",
                content_digest=sha("source-a"),
                rights_refs=("rights:fixture",),
                policy_refs=("policy:training-ok",),
            ),
            SourceRecord(
                source_id="source:b",
                content_digest=sha("source-b"),
                rights_refs=("rights:fixture",),
            ),
        )
        shards = (
            DatasetShardManifest(
                dataset_id="ds-a",
                shard_id="000",
                content_digest=sha("ds-a-000"),
                sample_count=3,
                source_ids=("source:a",),
            ),
            DatasetShardManifest(
                dataset_id="ds-b",
                shard_id="000",
                content_digest=sha("ds-b-000"),
                sample_count=2,
                source_ids=("source:b",),
            ),
        )
        mixture = MixtureManifest(
            mixture_id="mix-1",
            components=(
                MixtureComponent("ds-a", 3),
                MixtureComponent("ds-b", 1),
            ),
            seed=7,
        )
        return TrainingDataManifest(
            manifest_id="train-data-1",
            sources=sources,
            shards=shards,
            mixture=mixture,
            transform_refs=("transform:normalize-v1", "transform:dedupe-v2"),
            holdout_refs=("holdout:blind-promotion-v1",),
        )

    def test_manifest_root_is_deterministic(self) -> None:
        left = self.manifest()
        right = self.manifest()
        self.assertEqual(left.root_digest, right.root_digest)
        self.assertEqual(left.mixture.digest, right.mixture.digest)

    def test_weighted_schedule_is_integer_exact_and_replayable(self) -> None:
        mixture = self.manifest().mixture
        first = mixture.dataset_schedule(draws=16)
        second = mixture.dataset_schedule(draws=16)
        self.assertEqual(first, second)
        self.assertEqual(first.count("ds-a"), 12)
        self.assertEqual(first.count("ds-b"), 4)

    def test_checkpoint_cursor_binds_manifest_and_mixture(self) -> None:
        manifest = self.manifest()
        cursor = manifest.checkpoint_cursor(
            draw_index=10,
            dataset_offsets={"ds-a": 8, "ds-b": 2},
        )
        cursor.assert_compatible(manifest)
        self.assertEqual(len(cursor.digest), 64)

        altered = TrainingDataManifest(
            manifest_id=manifest.manifest_id,
            sources=manifest.sources,
            shards=manifest.shards,
            mixture=MixtureManifest(
                mixture_id="mix-1",
                components=(
                    MixtureComponent("ds-a", 1),
                    MixtureComponent("ds-b", 1),
                ),
                seed=7,
            ),
            transform_refs=manifest.transform_refs,
            holdout_refs=manifest.holdout_refs,
        )
        with self.assertRaisesRegex(TrainingLineageError, "manifest root mismatch"):
            cursor.assert_compatible(altered)

    def test_unknown_source_reference_fails_closed(self) -> None:
        base = self.manifest()
        bad_shard = DatasetShardManifest(
            dataset_id="ds-a",
            shard_id="bad",
            content_digest=sha("bad"),
            sample_count=1,
            source_ids=("source:missing",),
        )
        with self.assertRaisesRegex(TrainingLineageError, "unknown source"):
            TrainingDataManifest(
                manifest_id="bad",
                sources=base.sources,
                shards=(bad_shard, base.shards[1]),
                mixture=base.mixture,
            )

    def test_mixture_must_cover_exact_dataset_set(self) -> None:
        base = self.manifest()
        with self.assertRaisesRegex(TrainingLineageError, "coverage mismatch"):
            TrainingDataManifest(
                manifest_id="bad-mixture",
                sources=base.sources,
                shards=base.shards,
                mixture=MixtureManifest(
                    mixture_id="only-a",
                    components=(MixtureComponent("ds-a", 1),),
                ),
            )

    def test_duplicate_shard_identity_is_rejected(self) -> None:
        base = self.manifest()
        with self.assertRaisesRegex(TrainingLineageError, "identities must be unique"):
            TrainingDataManifest(
                manifest_id="dupe",
                sources=base.sources,
                shards=(base.shards[0], base.shards[0], base.shards[1]),
                mixture=base.mixture,
            )

    def test_rights_are_mandatory_at_source_root(self) -> None:
        with self.assertRaisesRegex(TrainingLineageError, "rights_refs"):
            SourceRecord(
                source_id="source:no-rights",
                content_digest=sha("source"),
                rights_refs=(),
            )


if __name__ == "__main__":
    unittest.main()
