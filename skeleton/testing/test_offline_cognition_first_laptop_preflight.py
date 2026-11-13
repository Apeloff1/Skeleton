"""Read-only first-laptop source preflight contract and rejection matrix.

The installed model receipt is intentionally MOCKED here. Passing these tests
does not imply GGUF native inference, valid third-party license or qualified
Windows/WSL2 hardware; those require independent external evidence.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import os
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError,Scope,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    sign_manifest_for_operator,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.first_laptop_preflight import (
    inspect_first_laptop,inspect_private_root,observed_host,main,
)

KEY=bytes(range(32))
MODEL="a"*64
TOKENIZER="b"*64
RAW=b"Exact operator approved source evidence for the offline laptop"
SCOPE=Scope("local","owner",MODEL,TOKENIZER)


class FirstLaptopPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.model=root/"model"
        self.model.mkdir(mode=0o700)
        self.sources=root/"source_data"
        self.sources.mkdir(mode=0o700)
        self.state=root/"native_state"
        self.state.mkdir(mode=0o700)
        self.queue=root/"work_order_state"
        self.queue.mkdir(mode=0o700)
        self.original=self.sources/"original.txt"
        self.original.write_bytes(RAW)
        self.original.chmod(0o600)
        self.manifest=root/"source_manifest.json"
        self.manifest.write_bytes(sign_manifest_for_operator({
            "schema":"offline-signed-source-manifest.v1",
            "tenant":"local","subject":"owner",
            "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
            "issued_at":100,"expires_at":200,"nonce":"f"*32,
            "sources":[{"source_id":"original","filename":"original.txt",
                        "sha256":__import__("hashlib").sha256(RAW).hexdigest(),
                        "rights_receipt_sha256":"c"*64,"approved":True}],
        },KEY))
        self.manifest.chmod(0o600)
        self.receipt=SimpleNamespace(
            model_sha256=MODEL,archive_sha256="d"*64,source_sha="e"*64,
            content_verified=True,rights_approved=True,
        )

    def inspect(self,**change):
        opts={
            "model_root":self.model,"source_root":self.sources,
            "source_manifest":self.manifest,"state_dir":self.state,
            "queue_dir":self.queue,"tenant":"local","subject":"owner",
            "operator_key":KEY,"observed_at":150,"context":2048,
            "max_output_tokens":128,"threads":4,"minimum_free_bytes":1,
        }
        opts.update(change)
        with patch(
            "skeleton.ai.runtime.operational_ai.laptop_runtime.installation.source_receipt",
            return_value=self.receipt,
        ) as receipt:
            result=inspect_first_laptop(**opts)
        return result,receipt

    def test_real_source_and_mocked_model_contract(self):
        result,receipt=self.inspect()
        self.assertTrue(result["original_source_bytes_verified"])
        self.assertTrue(result["source_manifest_hmac_verified"])
        self.assertTrue(result["installer_content_receipt_verified"])
        self.assertEqual(result["source_count"],1)
        self.assertEqual(result["source_bytes_total"],len(RAW))
        self.assertEqual(result["installed_model_sha256"],MODEL)
        self.assertEqual(receipt.call_count,1)

    def test_never_self_certify_native_or_release(self):
        result,_=self.inspect()
        self.assertFalse(result["real_native_model_loaded"])
        self.assertFalse(result["native_output_observed"])
        self.assertFalse(result["signed_work_order_created"])
        self.assertFalse(result["second_replay_observed"])
        self.assertFalse(result["model_legal_rights_independently_proved"])
        self.assertFalse(result["real_windows_device_qualified"])
        self.assertFalse(result["release_certified"])

    def test_preflight_does_not_write_sqlite_or_state(self):
        self.inspect()
        self.assertEqual(tuple(self.state.iterdir()),())
        self.assertEqual(tuple(self.queue.iterdir()),())

    def test_three_private_roots_observed(self):
        result,_=self.inspect()
        roots=result["private_root_observations"]
        self.assertEqual(len(roots),3)
        self.assertTrue(all(x["descriptor_anchored"] for x in roots))
        self.assertTrue(all(not x["state_db_integrity_checked"] for x in roots))

    def test_original_source_mutation_denied(self):
        self.original.write_bytes(b"altered original source")
        with self.assertRaises(CognitionError):
            self.inspect()

    def test_wrong_hmac_key_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(operator_key=bytes(reversed(range(32))))

    def test_signed_foreign_principal_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(subject="foreign")

    def test_expired_signed_manifest_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(observed_at=200)

    def test_future_signed_manifest_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(observed_at=99)

    def test_model_digest_mismatch_denied(self):
        self.receipt.model_sha256="f"*64
        with self.assertRaises(CognitionError):
            self.inspect()

    def test_unapproved_installed_model_denied(self):
        self.receipt.rights_approved=False
        with self.assertRaises(CognitionError):
            self.inspect()

    def test_missing_original_archive_receipt_denied(self):
        self.receipt.archive_sha256=""
        with self.assertRaises(CognitionError):
            self.inspect()

    def test_world_readable_source_root_denied(self):
        self.sources.chmod(0o755)
        with self.assertRaises(CognitionError):
            self.inspect()

    def test_unsafe_queue_ancestor_denied(self):
        alias=Path(self.temp.name)/"linked_parent"
        alias.symlink_to(Path(self.temp.name),target_is_directory=True)
        with self.assertRaises(CognitionError):
            self.inspect(queue_dir=alias/"work_order_state")

    def test_private_queue_symlink_denied(self):
        alias=Path(self.temp.name)/"linked_queue"
        alias.symlink_to(self.queue,target_is_directory=True)
        with self.assertRaises(CognitionError):
            self.inspect(queue_dir=alias)

    def test_relative_model_path_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(model_root=Path("relative-model"))

    def test_relative_state_path_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(state_dir=Path("relative-state"))

    def test_context_output_collision_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(context=128,max_output_tokens=128)

    def test_invalid_cpu_thread_count_denied(self):
        with self.assertRaises(CognitionError):
            self.inspect(threads=0)

    def test_source_file_hardlink_denied(self):
        os.link(self.original,self.sources/"other.txt")
        with self.assertRaises(CognitionError):
            self.inspect()

    def test_canonical_root_headroom_measured(self):
        observed=inspect_private_root(self.queue,label="queue",required_free_bytes=1)
        self.assertGreater(observed["available_bytes_observed"],0)
        self.assertFalse(observed["writable_probe_performed"])

    def test_low_disk_headroom_is_fail_closed(self):
        with patch(
            "skeleton.ai.runtime.operational_ai.offline_cognition.first_laptop_preflight.os.fstatvfs",
            return_value=SimpleNamespace(f_bavail=1,f_frsize=1),
        ):
            with self.assertRaises(CognitionError):
                inspect_private_root(self.queue,label="queue",required_free_bytes=1024)

    def test_source_key_not_echoed_in_status(self):
        result,_=self.inspect()
        self.assertNotIn(KEY.hex(),str(result))

    def test_not_linux_is_held(self):
        with patch(
            "skeleton.ai.runtime.operational_ai.offline_cognition.first_laptop_preflight.os.uname",
            return_value=SimpleNamespace(sysname="Darwin"),
        ):
            with self.assertRaises(CognitionError):
                observed_host()

    def test_command_without_environment_key_never_activates(self):
        argv=[
            "--model-root",str(self.model),
            "--state-dir",str(self.state),
            "--queue-dir",str(self.queue),
            "--source-root",str(self.sources),
            "--source-manifest",str(self.manifest),
            "--tenant","local","--subject","owner",
        ]
        with patch.dict(os.environ,{"SKELETON_OFFLINE_OPERATOR_KEY_HEX":""}):
            self.assertEqual(main(argv),2)


if __name__=="__main__":
    unittest.main()
