"""Hash-bound private artifact write/read and fail-closed replacement protection."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.operational_ai.native_supervised.artifact_store import publish,read
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


@unittest.skipUnless(os.name == "posix", "POSIX private descriptor custody")
class TestNativeSFTArtifactCustody(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=NativeLLMRuntime(TinyTransformer(
            vocab=("alpha","beta","gamma"),dim=8,ctx=32,seed=12,d_ff=0
        ))
        cls.raw=cls.native.checkpoint_json().encode("utf-8")

    def test_owner_private_roundtrip(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            folder=Path(parent)/"checkpoint"
            receipt=publish(
                folder,self.raw,model_sha256=self.native.model_digest,
                tokenizer_sha256=self.native.tokenizer.digest,
                kind="untrained-genesis",source_sha256="a"*64,
            )
            loaded=read(folder,receipt["checkpoint_sha256"])
            self.assertEqual(loaded,self.raw)
            self.assertEqual(receipt["kind"],"untrained-genesis")
            self.assertFalse(receipt["serving_activated"])

    def test_duplicate_immutable_artifact_refused(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            folder=Path(parent)/"checkpoint"
            kwargs=dict(model_sha256=self.native.model_digest,
                        tokenizer_sha256=self.native.tokenizer.digest,
                        kind="untrained-genesis",source_sha256="a"*64)
            publish(folder,self.raw,**kwargs)
            with self.assertRaises(SupervisedRejected):
                publish(folder,self.raw,**kwargs)

    def test_candidate_requires_training_proof(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            with self.assertRaises(SupervisedRejected):
                publish(Path(parent)/"checkpoint",self.raw,
                        model_sha256=self.native.model_digest,
                        tokenizer_sha256=self.native.tokenizer.digest,
                        kind="sft-candidate",source_sha256="a"*64)

    def test_model_hash_mismatch_refused(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            with self.assertRaises(SupervisedRejected):
                publish(Path(parent)/"checkpoint",self.raw,
                        model_sha256="f"*64,
                        tokenizer_sha256=self.native.tokenizer.digest,
                        kind="untrained-genesis",source_sha256="a"*64)

    def test_traversal_via_symlink_refused(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            root=Path(parent)
            root.joinpath("real").mkdir(mode=0o700)
            root.joinpath("link").symlink_to(root/"real",target_is_directory=True)
            with self.assertRaises((SupervisedRejected,OSError)):
                publish(root/"link",self.raw,
                        model_sha256=self.native.model_digest,
                        tokenizer_sha256=self.native.tokenizer.digest,
                        kind="untrained-genesis",source_sha256="a"*64)

    def test_bad_checkpoint_sha_denied_before_read(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            with self.assertRaises(SupervisedRejected):
                read(Path(parent),"not-sha")

    def test_missing_manifest_is_incomplete_artifact(self):
        with tempfile.TemporaryDirectory(dir=Path.home()) as parent:
            folder=Path(parent)/"checkpoint"
            receipt=publish(
                folder,self.raw,model_sha256=self.native.model_digest,
                tokenizer_sha256=self.native.tokenizer.digest,
                kind="untrained-genesis",source_sha256="a"*64,
            )
            manifest=folder/(receipt["checkpoint_sha256"]+".manifest.json")
            manifest.unlink()
            with self.assertRaises((SupervisedRejected,OSError)):
                read(folder,receipt["checkpoint_sha256"])


if __name__=="__main__":
    unittest.main()
