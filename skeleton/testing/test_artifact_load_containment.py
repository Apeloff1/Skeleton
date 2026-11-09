from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.artifact_loading import (
    ArtifactLoadError,
    ArtifactLoadPolicy,
    ArtifactLoadRequest,
    ArtifactShard,
    TensorDescriptor,
    admit_artifact,
    verify_shard_payload,
)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ArtifactLoadContainmentTests(unittest.TestCase):
    def request(self, payload: bytes = b"safe-weights") -> ArtifactLoadRequest:
        return ArtifactLoadRequest(
            artifact_id="model:test",
            weight_format="safetensors",
            shards=(
                ArtifactShard(
                    name="weights/00001.safetensors",
                    digest=sha(payload),
                    encoded_bytes=len(payload),
                    decoded_bytes=len(payload),
                    tensors=(
                        TensorDescriptor(
                            name="decoder.weight",
                            dtype="bf16",
                            shape=(64, 64),
                        ),
                    ),
                ),
            ),
            metadata_bytes=1024,
            safe_parser=True,
            embedded_executable_code=False,
        )

    def test_safe_artifact_is_admitted(self) -> None:
        request = self.request()
        receipt = admit_artifact(request, ArtifactLoadPolicy())
        self.assertTrue(receipt.admitted, receipt.blockers)
        self.assertEqual(receipt.tensor_count, 1)

    def test_unsafe_parser_fails_closed(self) -> None:
        request = self.request()
        unsafe = ArtifactLoadRequest(
            artifact_id=request.artifact_id,
            weight_format=request.weight_format,
            shards=request.shards,
            metadata_bytes=request.metadata_bytes,
            safe_parser=False,
            embedded_executable_code=False,
        )
        receipt = admit_artifact(unsafe, ArtifactLoadPolicy())
        self.assertFalse(receipt.admitted)
        self.assertIn("safe parser declaration is required", receipt.blockers)

    def test_decompression_bomb_is_rejected(self) -> None:
        shard = ArtifactShard(
            name="weights/compressed.safetensors",
            digest=sha(b"x"),
            encoded_bytes=1,
            decoded_bytes=1024,
        )
        request = ArtifactLoadRequest(
            artifact_id="model:bomb",
            weight_format="safetensors",
            shards=(shard,),
            metadata_bytes=0,
            safe_parser=True,
            embedded_executable_code=False,
        )
        receipt = admit_artifact(
            request,
            ArtifactLoadPolicy(max_decompression_ratio=8),
        )
        self.assertFalse(receipt.admitted)
        self.assertTrue(
            any("decompression ratio" in blocker for blocker in receipt.blockers)
        )

    def test_tensor_shape_and_dtype_are_bounded(self) -> None:
        shard = ArtifactShard(
            name="weights/bad.safetensors",
            digest=sha(b"x"),
            encoded_bytes=1,
            decoded_bytes=1,
            tensors=(
                TensorDescriptor(
                    name="huge",
                    dtype="object",
                    shape=(1024, 1024, 1024),
                ),
            ),
        )
        request = ArtifactLoadRequest(
            artifact_id="model:bad-tensor",
            weight_format="safetensors",
            shards=(shard,),
            metadata_bytes=0,
            safe_parser=True,
            embedded_executable_code=False,
        )
        receipt = admit_artifact(
            request,
            ArtifactLoadPolicy(max_tensor_elements=1_000_000),
        )
        self.assertFalse(receipt.admitted)
        self.assertTrue(any("dtype" in blocker for blocker in receipt.blockers))
        self.assertTrue(any("tensor elements" in blocker for blocker in receipt.blockers))

    def test_model_code_trust_is_separate_from_weight_trust(self) -> None:
        request = self.request()
        code_digest = sha(b"model-code")
        with_code = ArtifactLoadRequest(
            artifact_id=request.artifact_id,
            weight_format=request.weight_format,
            shards=request.shards,
            metadata_bytes=request.metadata_bytes,
            safe_parser=True,
            embedded_executable_code=False,
            model_code_digest=code_digest,
        )
        receipt = admit_artifact(with_code, ArtifactLoadPolicy())
        self.assertFalse(receipt.admitted)
        self.assertIn("model code has no independent trusted digest", receipt.blockers)

        trusted = ArtifactLoadRequest(
            artifact_id=request.artifact_id,
            weight_format=request.weight_format,
            shards=request.shards,
            metadata_bytes=request.metadata_bytes,
            safe_parser=True,
            embedded_executable_code=False,
            model_code_digest=code_digest,
            trusted_model_code_digest=code_digest,
        )
        self.assertTrue(admit_artifact(trusted, ArtifactLoadPolicy()).admitted)

    def test_embedded_executable_code_is_forbidden_by_default(self) -> None:
        request = self.request()
        executable = ArtifactLoadRequest(
            artifact_id=request.artifact_id,
            weight_format=request.weight_format,
            shards=request.shards,
            metadata_bytes=request.metadata_bytes,
            safe_parser=True,
            embedded_executable_code=True,
        )
        receipt = admit_artifact(executable, ArtifactLoadPolicy())
        self.assertFalse(receipt.admitted)
        self.assertIn("embedded executable model code is forbidden", receipt.blockers)

    def test_payload_digest_and_size_are_verified_before_parse(self) -> None:
        payload = b"safe-weights"
        request = self.request(payload)
        verify_shard_payload(request.shards[0], payload)
        with self.assertRaisesRegex(ArtifactLoadError, "digest mismatch"):
            verify_shard_payload(request.shards[0], b"tampered")

    def test_shard_path_cannot_escape_artifact_root(self) -> None:
        with self.assertRaisesRegex(ArtifactLoadError, "artifact-relative"):
            ArtifactShard(
                name="../weights.safetensors",
                digest=sha(b"x"),
                encoded_bytes=1,
                decoded_bytes=1,
            )


if __name__ == "__main__":
    unittest.main()
