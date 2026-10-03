from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.model_identity import (
    ModelArtifactManifest,
    ModelIdentityError,
    RepresentationSpec,
    WeightShard,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ModelIdentityTests(unittest.TestCase):
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

    def manifest(self) -> ModelArtifactManifest:
        return ModelArtifactManifest(
            model_id="skeleton-local-1",
            architecture_id="decoder-transformer-v1",
            architecture_config_digest=sha("arch"),
            representation=self.representation(),
            weight_shards=(
                WeightShard("weights/00001.safetensors", sha("weights-1"), 4096),
                WeightShard("weights/00002.safetensors", sha("weights-2"), 4096),
            ),
            weight_format="safetensors",
            dtype="bf16",
            quantization="none",
            model_code_digest=sha("model-code"),
            runtime_abi="skeleton.inference.v1",
            data_manifest_root=sha("dataset-root"),
            eval_evidence_root=sha("eval-root"),
            provenance_root=sha("provenance-root"),
            adapter_set=("adapter:reasoning",),
            kernel_capability_requirements=("attention.sdpa",),
        )

    def test_representation_identity_is_deterministic(self) -> None:
        left = self.representation()
        right = self.representation()
        self.assertEqual(left.representation_id, right.representation_id)
        self.assertTrue(left.representation_id.startswith("rep:"))

    def test_special_token_aliasing_is_rejected(self) -> None:
        with self.assertRaisesRegex(ModelIdentityError, "ids must be unique"):
            RepresentationSpec(
                tokenizer_family="byte-bpe",
                tokenizer_version="1",
                vocabulary_digest=sha("vocab"),
                normalization_spec="NFC",
                byte_fallback_policy="lossless",
                special_token_map={"<bos>": 1, "<eos>": 1},
            )

    def test_model_identity_binds_representation_lineage_and_runtime(self) -> None:
        manifest = self.manifest()
        payload = manifest.as_dict()
        self.assertEqual(
            payload["representation_id"],
            manifest.representation.representation_id,
        )
        self.assertEqual(payload["data_manifest_root"], sha("dataset-root"))
        self.assertEqual(payload["eval_evidence_root"], sha("eval-root"))
        self.assertEqual(payload["provenance_root"], sha("provenance-root"))
        self.assertTrue(manifest.artifact_id.startswith("model:"))

    def test_loaded_components_must_exactly_match_manifest(self) -> None:
        manifest = self.manifest()
        manifest.validate_loaded_components(
            representation_id=manifest.representation.representation_id,
            model_code_digest=sha("model-code"),
            runtime_abi="skeleton.inference.v1",
            weight_digests={
                "weights/00001.safetensors": sha("weights-1"),
                "weights/00002.safetensors": sha("weights-2"),
            },
        )
        with self.assertRaisesRegex(ModelIdentityError, "weight shard"):
            manifest.validate_loaded_components(
                representation_id=manifest.representation.representation_id,
                model_code_digest=sha("model-code"),
                runtime_abi="skeleton.inference.v1",
                weight_digests={
                    "weights/00001.safetensors": sha("tampered"),
                    "weights/00002.safetensors": sha("weights-2"),
                },
            )

    def test_representation_mismatch_fails_closed(self) -> None:
        manifest = self.manifest()
        other = RepresentationSpec(
            tokenizer_family="byte-bpe",
            tokenizer_version="2.0.0",
            vocabulary_digest=sha("vocab-2"),
            normalization_spec="NFC",
            byte_fallback_policy="lossless",
            special_token_map={"<bos>": 1, "<eos>": 2, "<pad>": 3},
            bos_token="<bos>",
            eos_token="<eos>",
            padding_token="<pad>",
        )
        with self.assertRaisesRegex(ModelIdentityError, "representation"):
            manifest.validate_loaded_components(
                representation_id=other.representation_id,
                model_code_digest=sha("model-code"),
                runtime_abi="skeleton.inference.v1",
                weight_digests={
                    "weights/00001.safetensors": sha("weights-1"),
                    "weights/00002.safetensors": sha("weights-2"),
                },
            )

    def test_weight_paths_cannot_escape_artifact_root(self) -> None:
        with self.assertRaisesRegex(ModelIdentityError, "relative"):
            WeightShard("../outside.safetensors", sha("bad"), 1)


if __name__ == "__main__":
    unittest.main()
