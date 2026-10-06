from __future__ import annotations

from collections import Counter
import hashlib
import unittest

from skeleton.ai.learning.artifact_loading import (
    ArtifactLoadError,
    ArtifactLoadPolicy,
    ArtifactLoadRequest,
    ArtifactShard,
    TensorDescriptor,
    admit_artifact,
    admit_artifact_evidence,
    bind_model_manifest,
)
from skeleton.ai.learning.model_identity import (
    ModelArtifactManifest,
    ModelIdentityError,
    RepresentationSpec,
    WeightShard,
)
from skeleton.ai.learning.training_lineage import (
    DatasetShardManifest,
    MixtureComponent,
    MixtureManifest,
    SourceRecord,
    TrainingCursor,
    TrainingDataManifest,
    TrainingLineageError,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ArtifactLineageIntegrityTests(unittest.TestCase):
    def representation(self) -> RepresentationSpec:
        return RepresentationSpec(
            tokenizer_family="byte-bpe",
            tokenizer_version="1.0.0",
            vocabulary_digest=sha("vocab"),
            normalization_spec="NFC",
            byte_fallback_policy="lossless",
            special_token_map={"<bos>": 1, "<eos>": 2, "<pad>": 3},
            bos_token="<bos>",
            eos_token="<eos>",
            padding_token="<pad>",
        )

    def model_manifest(self) -> ModelArtifactManifest:
        return ModelArtifactManifest(
            model_id="skeleton-integrity-fixture",
            architecture_id="decoder-v1",
            architecture_config_digest=sha("architecture"),
            representation=self.representation(),
            weight_shards=(
                WeightShard("weights/00001.safetensors", sha("weight-1"), 4096),
                WeightShard("weights/00002.safetensors", sha("weight-2"), 8192),
            ),
            weight_format="safetensors",
            dtype="bf16",
            quantization="none",
            model_code_digest=sha("model-code"),
            runtime_abi="skeleton.inference.v1",
            data_manifest_root=sha("training-data"),
            eval_evidence_root=sha("evaluation"),
            provenance_root=sha("provenance"),
        )

    def load_request(
        self,
        manifest: ModelArtifactManifest | None = None,
        *,
        embedded_code: bool = False,
        include_code_digest: bool = True,
        include_trusted_digest: bool = True,
    ) -> ArtifactLoadRequest:
        manifest = manifest or self.model_manifest()
        code_digest = manifest.model_code_digest if include_code_digest else None
        trusted = (
            manifest.model_code_digest
            if include_code_digest and include_trusted_digest
            else None
        )
        return ArtifactLoadRequest(
            artifact_id=manifest.artifact_id,
            weight_format=manifest.weight_format,
            shards=(
                ArtifactShard(
                    name="weights/00001.safetensors",
                    digest=sha("weight-1"),
                    encoded_bytes=4096,
                    decoded_bytes=4096,
                    tensors=(
                        TensorDescriptor(
                            name="decoder.embed.weight",
                            dtype="bf16",
                            shape=(16, 16),
                        ),
                    ),
                ),
                ArtifactShard(
                    name="weights/00002.safetensors",
                    digest=sha("weight-2"),
                    encoded_bytes=8192,
                    decoded_bytes=8192,
                    tensors=(
                        TensorDescriptor(
                            name="decoder.out.weight",
                            dtype="bf16",
                            shape=(16, 16),
                        ),
                    ),
                ),
            ),
            metadata_bytes=512,
            safe_parser=True,
            embedded_executable_code=embedded_code,
            model_code_digest=code_digest,
            trusted_model_code_digest=trusted,
        )

    def training_manifest(self) -> TrainingDataManifest:
        return TrainingDataManifest(
            manifest_id="training-integrity",
            sources=(
                SourceRecord(
                    source_id="source:a",
                    content_digest=sha("source-a"),
                    rights_refs=("rights:a",),
                ),
                SourceRecord(
                    source_id="source:b",
                    content_digest=sha("source-b"),
                    rights_refs=("rights:b",),
                ),
                SourceRecord(
                    source_id="source:c",
                    content_digest=sha("source-c"),
                    rights_refs=("rights:c",),
                ),
            ),
            shards=(
                DatasetShardManifest(
                    dataset_id="ds-a",
                    shard_id="000",
                    content_digest=sha("ds-a"),
                    sample_count=100,
                    source_ids=("source:a",),
                ),
                DatasetShardManifest(
                    dataset_id="ds-b",
                    shard_id="000",
                    content_digest=sha("ds-b"),
                    sample_count=100,
                    source_ids=("source:b",),
                ),
                DatasetShardManifest(
                    dataset_id="ds-c",
                    shard_id="000",
                    content_digest=sha("ds-c"),
                    sample_count=100,
                    source_ids=("source:c",),
                ),
            ),
            mixture=MixtureManifest(
                mixture_id="mix-integrity",
                components=(
                    MixtureComponent("ds-a", 5),
                    MixtureComponent("ds-b", 3),
                    MixtureComponent("ds-c", 2),
                ),
                seed=2,
            ),
        )

    def test_model_manifest_binds_exact_load_request(self) -> None:
        manifest = self.model_manifest()
        request = self.load_request(manifest)
        binding = bind_model_manifest(manifest, request)
        evidence = admit_artifact_evidence(request, ArtifactLoadPolicy())

        self.assertEqual(binding.artifact_id, manifest.artifact_id)
        self.assertEqual(binding.manifest_weight_identity, manifest.weight_identity)
        self.assertEqual(binding.request_digest, request.digest)
        self.assertTrue(evidence.receipt.admitted, evidence.receipt.blockers)
        self.assertEqual(evidence.request_digest, request.digest)
        self.assertEqual(evidence.policy_digest, ArtifactLoadPolicy().digest)
        self.assertEqual(binding.digest, bind_model_manifest(manifest, request).digest)
        self.assertEqual(
            evidence.digest,
            admit_artifact_evidence(request, ArtifactLoadPolicy()).digest,
        )

    def test_manifest_binding_rejects_artifact_identity_rebinding(self) -> None:
        manifest = self.model_manifest()
        request = self.load_request(manifest)
        rebound = ArtifactLoadRequest(
            artifact_id="model:" + sha("different"),
            weight_format=request.weight_format,
            shards=request.shards,
            metadata_bytes=request.metadata_bytes,
            safe_parser=request.safe_parser,
            embedded_executable_code=request.embedded_executable_code,
            model_code_digest=request.model_code_digest,
            trusted_model_code_digest=request.trusted_model_code_digest,
        )
        with self.assertRaisesRegex(ArtifactLoadError, "artifact identity"):
            bind_model_manifest(manifest, rebound)

    def test_manifest_binding_rejects_shard_digest_or_size_drift(self) -> None:
        manifest = self.model_manifest()
        request = self.load_request(manifest)
        bad_shard = ArtifactShard(
            name=request.shards[0].name,
            digest=sha("tampered-weight"),
            encoded_bytes=request.shards[0].encoded_bytes,
            decoded_bytes=request.shards[0].decoded_bytes,
            tensors=request.shards[0].tensors,
        )
        drifted = ArtifactLoadRequest(
            artifact_id=request.artifact_id,
            weight_format=request.weight_format,
            shards=(bad_shard, request.shards[1]),
            metadata_bytes=request.metadata_bytes,
            safe_parser=True,
            embedded_executable_code=False,
            model_code_digest=request.model_code_digest,
            trusted_model_code_digest=request.trusted_model_code_digest,
        )
        with self.assertRaisesRegex(ArtifactLoadError, "shard set/digest/size"):
            bind_model_manifest(manifest, drifted)

    def test_manifest_binding_rejects_model_code_rebinding(self) -> None:
        manifest = self.model_manifest()
        request = self.load_request(manifest)
        rebound = ArtifactLoadRequest(
            artifact_id=request.artifact_id,
            weight_format=request.weight_format,
            shards=request.shards,
            metadata_bytes=request.metadata_bytes,
            safe_parser=True,
            embedded_executable_code=False,
            model_code_digest=sha("different-code"),
            trusted_model_code_digest=sha("different-code"),
        )
        with self.assertRaisesRegex(ArtifactLoadError, "model code identity"):
            bind_model_manifest(manifest, rebound)

    def test_embedded_executable_code_requires_digest_even_when_policy_allows_it(self) -> None:
        request = self.load_request(
            embedded_code=True,
            include_code_digest=False,
            include_trusted_digest=False,
        )
        receipt = admit_artifact(
            request,
            ArtifactLoadPolicy(allow_embedded_executable_code=True),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn(
            "embedded executable model code has no content digest",
            receipt.blockers,
        )

    def test_embedded_executable_code_still_requires_independent_trust(self) -> None:
        request = self.load_request(
            embedded_code=True,
            include_code_digest=True,
            include_trusted_digest=False,
        )
        receipt = admit_artifact(
            request,
            ArtifactLoadPolicy(allow_embedded_executable_code=True),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("model code has no independent trusted digest", receipt.blockers)

        trusted = self.load_request(embedded_code=True)
        admitted = admit_artifact(
            trusted,
            ArtifactLoadPolicy(allow_embedded_executable_code=True),
        )
        self.assertTrue(admitted.admitted, admitted.blockers)

    def test_global_tensor_name_collision_across_shards_fails_closed(self) -> None:
        duplicate = TensorDescriptor(
            name="shared.weight",
            dtype="bf16",
            shape=(2, 2),
        )
        with self.assertRaisesRegex(ArtifactLoadError, "globally unique"):
            ArtifactLoadRequest(
                artifact_id="model:" + sha("duplicate-tensors"),
                weight_format="safetensors",
                shards=(
                    ArtifactShard(
                        name="weights/a.safetensors",
                        digest=sha("a"),
                        encoded_bytes=1,
                        decoded_bytes=1,
                        tensors=(duplicate,),
                    ),
                    ArtifactShard(
                        name="weights/b.safetensors",
                        digest=sha("b"),
                        encoded_bytes=1,
                        decoded_bytes=1,
                        tensors=(duplicate,),
                    ),
                ),
                metadata_bytes=0,
                safe_parser=True,
                embedded_executable_code=False,
            )

    def test_aggregate_tensor_budgets_block_many_small_tensors(self) -> None:
        request = ArtifactLoadRequest(
            artifact_id="model:" + sha("tensor-budget"),
            weight_format="safetensors",
            shards=(
                ArtifactShard(
                    name="weights/budget.safetensors",
                    digest=sha("budget"),
                    encoded_bytes=64,
                    decoded_bytes=64,
                    tensors=(
                        TensorDescriptor("a", "bf16", (8, 8)),
                        TensorDescriptor("b", "bf16", (8, 8)),
                    ),
                ),
            ),
            metadata_bytes=0,
            safe_parser=True,
            embedded_executable_code=False,
        )
        receipt = admit_artifact(
            request,
            ArtifactLoadPolicy(max_tensors=1, max_total_tensor_elements=100),
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("tensor count exceeds policy", receipt.blockers)
        self.assertIn("total tensor elements exceed policy", receipt.blockers)

    def test_policy_boolean_type_confusion_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, "require_safe_parser"):
            ArtifactLoadPolicy(require_safe_parser=1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(TypeError, "allow_embedded_executable_code"):
            ArtifactLoadPolicy(allow_embedded_executable_code=0)  # type: ignore[arg-type]

    def test_artifact_paths_must_be_canonical_and_platform_neutral(self) -> None:
        for bad in (
            "../weights.safetensors",
            "weights//a.safetensors",
            " weights/a.safetensors",
            "C:/weights/a.safetensors",
            "weights\\a.safetensors",
            "weights/\x00bad.safetensors",
        ):
            with self.subTest(path=repr(bad)):
                with self.assertRaisesRegex(ArtifactLoadError, "canonical artifact-relative"):
                    ArtifactShard(
                        name=bad,
                        digest=sha("bad"),
                        encoded_bytes=1,
                        decoded_bytes=1,
                    )

        for bad in ("weights//a.safetensors", "C:/weights/a.safetensors"):
            with self.subTest(identity_path=bad):
                with self.assertRaisesRegex(ModelIdentityError, "canonical artifact-relative"):
                    WeightShard(bad, sha("bad"), 1)

    def test_special_token_names_cannot_alias_after_normalization(self) -> None:
        with self.assertRaisesRegex(ModelIdentityError, "after normalization"):
            RepresentationSpec(
                tokenizer_family="byte-bpe",
                tokenizer_version="1",
                vocabulary_digest=sha("vocab"),
                normalization_spec="NFC",
                byte_fallback_policy="lossless",
                special_token_map={"<bos>": 1, " <bos>": 2},
            )

    def test_loaded_weight_path_alias_is_rejected_before_comparison(self) -> None:
        manifest = self.model_manifest()
        with self.assertRaisesRegex(ModelIdentityError, "canonical artifact-relative"):
            manifest.validate_loaded_components(
                representation_id=manifest.representation.representation_id,
                model_code_digest=manifest.model_code_digest,
                runtime_abi=manifest.runtime_abi,
                weight_digests={
                    " weights/00001.safetensors": sha("weight-1"),
                    "weights/00002.safetensors": sha("weight-2"),
                },
            )

    def test_weight_identity_binds_shard_size_and_digest(self) -> None:
        manifest = self.model_manifest()
        changed = ModelArtifactManifest(
            model_id=manifest.model_id,
            architecture_id=manifest.architecture_id,
            architecture_config_digest=manifest.architecture_config_digest,
            representation=manifest.representation,
            weight_shards=(
                WeightShard("weights/00001.safetensors", sha("weight-1"), 4097),
                manifest.weight_shards[1],
            ),
            weight_format=manifest.weight_format,
            dtype=manifest.dtype,
            quantization=manifest.quantization,
            model_code_digest=manifest.model_code_digest,
            runtime_abi=manifest.runtime_abi,
            data_manifest_root=manifest.data_manifest_root,
            eval_evidence_root=manifest.eval_evidence_root,
            provenance_root=manifest.provenance_root,
        )
        self.assertNotEqual(manifest.weight_identity, changed.weight_identity)
        self.assertNotEqual(manifest.artifact_id, changed.artifact_id)

    def test_fast_dataset_draw_counts_match_reference_schedule(self) -> None:
        mixture = self.training_manifest().mixture
        for draws in range(0, 81):
            with self.subTest(draws=draws):
                reference = Counter(mixture.dataset_schedule(draws=draws))
                counts = mixture.dataset_draw_counts(draws=draws)
                self.assertEqual(
                    counts,
                    {
                        component.dataset_id: reference[component.dataset_id]
                        for component in mixture.components
                    },
                )

    def test_large_cursor_counts_do_not_require_full_schedule_materialization(self) -> None:
        manifest = self.training_manifest()
        draws = 1_000_003
        counts = manifest.expected_dataset_offsets(draw_index=draws)
        self.assertEqual(sum(counts.values()), draws)
        cursor = manifest.derived_checkpoint_cursor(draw_index=draws)
        cursor.assert_compatible(manifest)
        self.assertEqual(dict(cursor.dataset_offsets), counts)

    def test_checkpoint_cursor_rejects_forged_dataset_offsets(self) -> None:
        manifest = self.training_manifest()
        expected = manifest.expected_dataset_offsets(draw_index=100)
        forged = dict(expected)
        forged["ds-a"] += 1
        forged["ds-b"] -= 1

        with self.assertRaisesRegex(TrainingLineageError, "deterministic mixture schedule"):
            manifest.checkpoint_cursor(
                draw_index=100,
                dataset_offsets=forged,
            )

    def test_manually_constructed_cursor_cannot_bypass_offset_validation(self) -> None:
        manifest = self.training_manifest()
        cursor = TrainingCursor(
            manifest_root=manifest.root_digest,
            mixture_digest=manifest.mixture.digest,
            draw_index=10,
            dataset_offsets={"ds-a": 10, "ds-b": 0, "ds-c": 0},
        )
        with self.assertRaisesRegex(TrainingLineageError, "deterministic mixture schedule"):
            cursor.assert_compatible(manifest)

    def test_cursor_dataset_keys_cannot_alias_after_normalization(self) -> None:
        manifest = self.training_manifest()
        with self.assertRaisesRegex(TrainingLineageError, "collide after normalization"):
            TrainingCursor(
                manifest_root=manifest.root_digest,
                mixture_digest=manifest.mixture.digest,
                draw_index=1,
                dataset_offsets={"ds-a": 1, " ds-a": 0, "ds-b": 0, "ds-c": 0},
            )

    def test_lineage_component_digests_are_deterministic(self) -> None:
        manifest = self.training_manifest()
        self.assertEqual(manifest.sources[0].digest, manifest.sources[0].digest)
        self.assertEqual(manifest.shards[0].digest, manifest.shards[0].digest)
        self.assertEqual(len(manifest.sources[0].digest), 64)
        self.assertEqual(len(manifest.shards[0].digest), 64)


if __name__ == "__main__":
    unittest.main()
