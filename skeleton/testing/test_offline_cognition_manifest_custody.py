"""Hostile signed-source and fd-anchored original-byte custody regressions.

No test creates a GGUF model, signs external license rights or executes inference.
The operator HMAC test key is a fixed NON-PRODUCTION fixture.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError,Scope,canonical,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    ManifestSource,SignedSourceManifest,verify_signed_manifest,
    sign_manifest_for_operator,ingest_authorized_sources,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli import (
    _environment_key,_read_private_manifest,run as live_run,
)
from scripts.sign_offline_ai_source_manifest import _publish_private

KEY=bytes(range(32))
OTHER_KEY=bytes(reversed(range(32)))
MODEL="a"*64
TOKENIZER="b"*64
RIGHTS="d"*64
SCOPE=Scope("local","owner",MODEL,TOKENIZER)

def record(raw=b"Original operator-reviewed source bytes", *,
           issued_at=100,expires_at=200,filename="source.txt"):
    return {
        "schema":"offline-signed-source-manifest.v1",
        "tenant":"local","subject":"owner",
        "model_sha256":MODEL,"tokenizer_sha256":TOKENIZER,
        "issued_at":issued_at,"expires_at":expires_at,
        "nonce":"f"*32,
        "sources":[{"source_id":"document","filename":filename,
                    "sha256":hashlib.sha256(raw).hexdigest(),
                    "rights_receipt_sha256":RIGHTS,"approved":True}],
    }

def signed(row):
    return sign_manifest_for_operator(row,KEY)

class ManifestSignatureTests(unittest.TestCase):
    def test_exact_hmac_accepts_finite_record(self):
        result=verify_signed_manifest(signed(record()),KEY,observed_at=150)
        self.assertEqual(result.scope,SCOPE)
        self.assertEqual(result.sources[0].filename,"source.txt")
        self.assertEqual(len(result.signed_record_sha256),64)

    def test_wrong_operator_key_denied(self):
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(record()),OTHER_KEY,observed_at=150)

    def test_signature_tampering_denied(self):
        obj=json.loads(signed(record()))
        obj["record"]["tenant"]="cross_tenant"
        with self.assertRaises(CognitionError):
            verify_signed_manifest(canonical(obj),KEY,observed_at=150)

    def test_future_and_expired_grant_denied(self):
        for observed in (99,200,300):
            with self.subTest(observed=observed):
                with self.assertRaises(CognitionError):
                    verify_signed_manifest(signed(record()),KEY,observed_at=observed)

    def test_overlong_hmac_validity_denied(self):
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(record(issued_at=100,expires_at=3701)),
                                   KEY,observed_at=200)

    def test_missing_explicit_source_approval_denied(self):
        value=record()
        value["sources"][0]["approved"]=False
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_duplicate_ids_denied(self):
        value=record()
        value["sources"].append({**value["sources"][0],"filename":"other.txt"})
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_duplicate_filenames_denied(self):
        value=record()
        value["sources"].append({**value["sources"][0],"source_id":"second"})
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_unknown_operator_authority_field_denied(self):
        value=record()
        value["force_native_execution"]=True
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_unknown_source_receipt_field_denied(self):
        value=record()
        value["sources"][0]["shell"]=True
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_unsafe_filename_denied(self):
        names=("../secret","..","/tmp/secret",".","./source.txt",
               "dir/source.txt","dir\\source.txt","source..txt",
               "☃.txt","source name.txt","a"*129)
        for name in names:
            with self.subTest(filename=name):
                value=record(filename=name)
                with self.assertRaises(CognitionError):
                    verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_more_than_eight_source_receipts_denied(self):
        value=record()
        value["sources"]=[{**value["sources"][0],
            "source_id":"doc"+str(i),"filename":"doc"+str(i)+".txt"}
            for i in range(9)]
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(value),KEY,observed_at=150)

    def test_malformed_json_duplicate_key_denied(self):
        data=b'{"record":{},"record":{},"mac":"'+b"a"*64+b'"}'
        with self.assertRaises(CognitionError):
            verify_signed_manifest(data,KEY,observed_at=150)

    def test_nonhex_operator_mac_denied(self):
        obj=json.loads(signed(record()))
        obj["mac"]="z"*64
        with self.assertRaises(CognitionError):
            verify_signed_manifest(canonical(obj),KEY,observed_at=150)

    def test_short_operator_secret_denied(self):
        with self.assertRaises(CognitionError):
            sign_manifest_for_operator(record(),b"short")

    def test_unsigned_source_cannot_create_fake_approval(self):
        raw=canonical({"record":record(),"mac":"0"*64})
        with self.assertRaises(CognitionError):
            verify_signed_manifest(raw,KEY,observed_at=150)

    def test_scope_bound_to_signed_source(self):
        manifest=verify_signed_manifest(signed(record()),KEY,observed_at=150)
        with self.assertRaises(CognitionError):
            SCOPE.assert_same(Scope("another","owner",MODEL,TOKENIZER))

    def test_rights_sha_is_explicit_but_not_independent_license_proof(self):
        manifest=verify_signed_manifest(signed(record()),KEY,observed_at=150)
        self.assertEqual(manifest.sources[0].rights_receipt_sha256,RIGHTS)
        self.assertFalse(hasattr(manifest,"independent_legal_review_proved"))


class PrivateSourceFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)/"sources"
        self.folder.mkdir(mode=0o700)
        self.original=b"Original operator-reviewed source bytes"
        self.file=self.folder/"source.txt"
        self.file.write_bytes(self.original)
        self.file.chmod(0o600)
        self.manifest=verify_signed_manifest(
            signed(record(self.original)),KEY,observed_at=150)

    def ingest(self,manifest=None,scope=SCOPE,root=None):
        return ingest_authorized_sources(
            self.folder if root is None else root,
            self.manifest if manifest is None else manifest,
            scope=scope,observed_at=150)

    def test_signed_regular_source_bytes_index(self):
        result=self.ingest()
        self.assertEqual(result.tenant,"local")
        self.assertEqual(result.subject,"owner")
        self.assertEqual(result.documents["document"].payload,self.original)

    def test_modified_original_sha_denied(self):
        self.file.write_bytes(b"Changed operator source")
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_cross_subject_denied_before_read(self):
        other=Scope("local","foreign",MODEL,TOKENIZER)
        with self.assertRaises(CognitionError):
            self.ingest(scope=other)

    def test_symlink_file_denied(self):
        self.file.unlink()
        elsewhere=self.folder/"another.txt"
        elsewhere.write_bytes(self.original)
        self.file.symlink_to(elsewhere)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_symlink_directory_denied(self):
        linked=Path(self.temp.name)/"linked"
        linked.symlink_to(self.folder,target_is_directory=True)
        with self.assertRaises(CognitionError):
            self.ingest(root=linked)

    def test_source_symlinked_ancestor_denied(self):
        linked=Path(self.temp.name)/"alias_source_parent"
        linked.symlink_to(Path(self.temp.name),target_is_directory=True)
        with self.assertRaises(CognitionError):
            self.ingest(root=linked/"sources")

    def test_fifo_denied(self):
        self.file.unlink()
        os.mkfifo(self.file)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_world_writable_source_denied(self):
        self.file.chmod(0o666)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_source_root_mode_0755_denied(self):
        # Ordinary non-writable access is not enough; owner-only 0700 required.
        self.folder.chmod(0o755)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_world_writable_root_denied(self):
        self.folder.chmod(0o777)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_hardlink_source_denied(self):
        other=self.folder/"another.txt"
        os.link(self.file,other)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_zero_byte_source_denied(self):
        self.file.write_bytes(b"")
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_overlarge_source_denied_without_reading(self):
        self.file.write_bytes(b"x"*262145)
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_missing_source_denied(self):
        self.file.unlink()
        with self.assertRaises(CognitionError):
            self.ingest()

    def test_filename_swap_during_original_read_denied(self):
        # Simulate swapping the path after the descriptor has opened and
        # original bytes were read. Original inode remains pinned by fd.
        original_os_read=os.read
        triggered=[False]
        def swapping_read(fd,size):
            out=original_os_read(fd,size)
            if not triggered[0]:
                triggered[0]=True
                renamed=self.folder/"renamed.txt"
                self.file.rename(renamed)
                self.file.write_bytes(self.original)
            return out
        with patch(
            "skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody.os.read",
            side_effect=swapping_read,
        ):
            with self.assertRaises(CognitionError):
                self.ingest()
        self.assertTrue(triggered[0])

    def test_wrong_signature_rejected_prior_to_file_io(self):
        with self.assertRaises(CognitionError):
            verify_signed_manifest(signed(record()),OTHER_KEY,observed_at=150)

    def test_private_manifest_finite_reader(self):
        manifest_file=Path(self.temp.name)/"operator_signed.json"
        manifest_file.write_bytes(signed(record()))
        manifest_file.chmod(0o600)
        self.assertEqual(_read_private_manifest(manifest_file),signed(record()))

    def test_manifest_parent_mode_0755_denied(self):
        raw=Path(self.temp.name)/"manifest.json"
        raw.write_bytes(signed(record()))
        raw.chmod(0o600)
        Path(self.temp.name).chmod(0o755)
        with self.assertRaises(CognitionError):
            _read_private_manifest(raw)

    def test_private_manifest_symlink_rejected(self):
        original=Path(self.temp.name)/"manifest.json"
        original.write_bytes(signed(record()))
        alias=Path(self.temp.name)/"manifest_link.json"
        alias.symlink_to(original)
        with self.assertRaises(CognitionError):
            _read_private_manifest(alias)

    def test_manifest_symlinked_ancestor_denied(self):
        raw=Path(self.temp.name)/"manifest_parent.json"
        raw.write_bytes(signed(record()))
        raw.chmod(0o600)
        linked=Path(self.temp.name)/"alias_manifest_parent"
        linked.symlink_to(Path(self.temp.name),target_is_directory=True)
        with self.assertRaises(CognitionError):
            _read_private_manifest(linked/"manifest_parent.json")

    def test_private_output_symlinked_ancestor_denied(self):
        linked=Path(self.temp.name)/"alias_output_parent"
        linked.symlink_to(Path(self.temp.name),target_is_directory=True)
        with self.assertRaises(CognitionError):
            _publish_private(linked/"signed.json",signed(record()))
        self.assertFalse((Path(self.temp.name)/"signed.json").exists())

    def test_private_output_is_exclusive_and_mode_0600(self):
        out=Path(self.temp.name)/"signed.json"
        data=signed(record())
        _publish_private(out,data)
        self.assertEqual(out.read_bytes(),data)
        self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
        with self.assertRaises(CognitionError):
            _publish_private(out,data)

    def test_private_output_root_writable_rejected(self):
        dest=self.folder/"operator_signed.json"
        self.folder.chmod(0o777)
        with self.assertRaises(CognitionError):
            _publish_private(dest,signed(record()))

    def test_full_laptop_command_no_approval_cannot_activate_model(self):
        argv=["--model-root","/nonexistent","--state-dir","/nonexistent",
              "--queue-dir","/nonexistent","--source-root",str(self.folder),
              "--source-manifest",str(self.file),"--tenant","local",
              "--subject","owner","--prompt-stdin"]
        self.assertEqual(live_run(argv),2)

    def test_absent_key_fails_before_native_activation(self):
        argv=["--model-root","/nonexistent","--state-dir","/nonexistent",
              "--queue-dir","/nonexistent","--source-root",str(self.folder),
              "--source-manifest",str(self.file),"--tenant","local",
              "--subject","owner","--prompt-stdin","--approve-native"]
        with patch.dict(os.environ,{"SKELETON_OFFLINE_OPERATOR_KEY_HEX":""}):
            self.assertEqual(live_run(argv),2)


if __name__=="__main__":
    unittest.main()
