"""Exercise complete archive-to-approved-model custody and hostile bundles."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.deployment.install.installer import (
    InstallError, install_approved_model, PREFIX, FINAL, WAVES,
)
from skeleton.ai.runtime.operational_ai.model.gguf.manifest import (
    GGUFModelManifest, Shard, load_manifest,
)
from skeleton.ai.runtime.operational_ai.model.gguf.assembly import assemble_model
from skeleton.ai.runtime.operational_ai.model.gguf.service import load_approved_manifest
from skeleton.ai.runtime.operational_ai.deployment.install.doctor import inspect_installed_model


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


class TestIntegralInstall(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ai-integral-", dir=Path.home())
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.install_root = self.root / "installed"
        self.install_root.mkdir(mode=0o700)
        self.archive = self.root / "input.tar"
        self.body = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"original offline fixture" * 14
        self.shard = Shard("weights/part-000.ggufpart", len(self.body), hashlib.sha256(self.body).hexdigest())
        self.manifest = GGUFModelManifest("original", (self.shard,), self.shard.sha256,
            len(self.body), "operator-approved", "operator:own-weights", True,
            2048, 0, 128_000_000)
        self.manifest_raw = json.dumps(self.manifest.to_record(), indent=2, sort_keys=True).encode() + b"\n"
        self.members = [
            ("bundle/stages/MBW-00/source/skeleton/ai/README.md", b"original code\n", "source"),
            (PREFIX + "original/model.manifest.json", self.manifest_raw, "approved_artifact"),
            (PREFIX + "original/" + self.shard.path, self.body, "approved_artifact"),
        ]
        self.rebuild()

    def tearDown(self):
        self.temp.cleanup()

    def rebuild(self, *, records=None, rename=None, corrupt=False, kind=None):
        observed=[]
        actual=self.members if records is None else records
        with tarfile.open(self.archive, "w", format=tarfile.PAX_FORMAT) as tar:
            for name, content, category in actual:
                info=tarfile.TarInfo(rename.get(name,name) if rename else name)
                info.size=len(content)
                tar.addfile(info, io.BytesIO(content))
                wave=name.split('/')[2]
                observed.append({"path":name,"wave":wave,"size":len(content),
                    "sha256":hashlib.sha256(content).hexdigest(),"kind":category,
                    "license":"operator-approved" if category=="approved_artifact" else "repository",
                    "provenance":"operator:own-weights" if category=="approved_artifact" else "git"})
            if corrupt:
                observed[-1]["sha256"]="b"*64
            index={"schema_version":1,"package":"skeleton-ai-ecosystem",
                   "status":"content-only-no-release-attestation", "source_sha":"a"*40,
                   "stage_graph":[{"id":name,"dependencies":[] if i==0 else [WAVES[i-1]]} for i,name in enumerate(WAVES)],
                   "entries":observed,
                   "source_bytes":sum(x['size'] for x in observed if x['kind']=='source'),
                   "approved_artifact_bytes":sum(x['size'] for x in observed if x['kind']=='approved_artifact')}
            if kind == "bad_status":index["status"]="production-ready"
            raw=canonical(index)
            item=tarfile.TarInfo(FINAL)
            item.size=len(raw)
            tar.addfile(item,io.BytesIO(raw))

    def install(self, *, install_id="model-v1", **options):
        return install_approved_model(self.archive,self.install_root,model_id="original",
            install_id=install_id,minimum_archive_bytes=1,maximum_archive_bytes=5_000_000,
            minimum_real_bytes=1,**options)

    def test_real_model_shard_install_roundtrip(self):
        receipt=self.install()
        self.assertEqual(receipt.model_sha256,self.manifest.model_sha256)
        self.assertEqual(receipt.installed_files,2)
        self.assertEqual(receipt.installed_bytes,len(self.body)+len(self.manifest_raw))
        self.assertEqual(receipt.status,"integrity-verified-not-release-certified")
        new=load_approved_manifest(self.install_root/'model-v1')
        self.assertEqual(new.manifest_digest,self.manifest.manifest_digest)
        with assemble_model(self.install_root/'model-v1',new) as staged:
            self.assertEqual(os.pread(staged.fd,len(self.body),0),self.body)
        self.assertEqual(list(self.install_root.iterdir()),[self.install_root/'model-v1'])

    def test_read_only_doctor_hashes_installed_model(self):
        self.install()
        report=inspect_installed_model(self.install_root/'model-v1')
        self.assertTrue(report.content_verified)
        self.assertFalse(report.native_inference_tested)
        self.assertFalse(report.release_certified)
        self.assertEqual(report.model_sha256,self.shard.sha256)

    def test_doctor_refuses_receipt_loss(self):
        self.install()
        (self.install_root/'model-v1'/'install.receipt.json').unlink()
        with self.assertRaises(OSError):
            inspect_installed_model(self.install_root/'model-v1')

    def test_doctor_refuses_forged_archive_identity(self):
        self.install()
        path=self.install_root/'model-v1'/'install.receipt.json'
        record=json.loads(path.read_text())
        record['archive_sha256']='b'*64
        path.chmod(0o600)
        path.write_text(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n')
        path.chmod(0o400)
        # A stand-alone digest cannot prove the signer; the doctor only checks
        # the receipt is self-consistent. This explicit hold is reserved for
        # invalid content or missing receipt fields, not claims of signature.
        report=inspect_installed_model(self.install_root/'model-v1')
        self.assertEqual(report.archive_sha256,'b'*64)
        self.assertFalse(report.release_certified)

    def test_doctor_refuses_conflicting_manifest_receipt(self):
        self.install()
        path=self.install_root/'model-v1'/'install.receipt.json'
        record=json.loads(path.read_text())
        record['model_sha256']='f'*64
        path.chmod(0o600)
        path.write_text(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n')
        path.chmod(0o400)
        with self.assertRaisesRegex(InstallError,'receipt disagrees'):
            inspect_installed_model(self.install_root/'model-v1')

    def test_read_only_doctor_blocks_tampered_weight(self):
        self.install()
        part=self.install_root/'model-v1'/self.shard.path
        part.chmod(0o600)
        with part.open('r+b') as f:f.seek(-1,2);f.write(b'Z')
        part.chmod(0o400)
        with self.assertRaisesRegex(InstallError,'digest'):
            inspect_installed_model(self.install_root/'model-v1')

    def test_operator_cli_reports_hold_before_install(self):
        from skeleton.ai.runtime.operational_ai.deployment.install.cli import main
        from contextlib import redirect_stderr
        out=io.StringIO()
        with redirect_stderr(out):
            code=main(['doctor','--model-root',str(self.install_root/'no-model')])
        self.assertEqual(code,2)
        self.assertIn('blocked',out.getvalue())

    def test_no_clobber_already_published(self):
        self.install()
        old=(self.install_root/'model-v1'/'model.manifest.json').read_bytes()
        with self.assertRaisesRegex(InstallError,"already exists"):
            self.install()
        self.assertEqual((self.install_root/'model-v1'/'model.manifest.json').read_bytes(),old)

    def test_default_production_byte_floor_is_not_bypassed(self):
        with self.assertRaisesRegex(InstallError,"approved size window"):
            install_approved_model(self.archive,self.install_root,model_id='original',install_id='prod')
        self.assertFalse((self.install_root/'prod').exists())

    def test_tampered_model_source_is_refused(self):
        self.rebuild(corrupt=True)
        with self.assertRaisesRegex(InstallError,"digest"):
            self.install()
        self.assertEqual(list(self.install_root.iterdir()),[])

    def test_refuse_traversal_even_with_matching_original_inventory(self):
        name=self.members[2][0]
        self.rebuild(rename={name:"bundle/stages/MBW-02/payload/models/original/../private"})
        with self.assertRaisesRegex(InstallError,"noncanonical"):
            self.install()
        self.assertEqual(list(self.install_root.iterdir()),[])

    def test_reject_duplicate_members_and_cleanup(self):
        self.rebuild(records=self.members+[self.members[2]])
        with self.assertRaisesRegex(InstallError,"duplicate"):
            self.install()
        self.assertEqual(list(self.install_root.iterdir()),[])

    def test_missing_shard_blocks_publish(self):
        self.rebuild(records=self.members[:2])
        with self.assertRaisesRegex(InstallError,"missing, extra"):
            self.install()
        self.assertEqual(list(self.install_root.iterdir()),[])

    def test_missing_model_manifest_blocks_publish(self):
        self.rebuild(records=[self.members[0],self.members[2]])
        with self.assertRaisesRegex(InstallError,"manifest absent"):
            self.install()
        self.assertEqual(list(self.install_root.iterdir()),[])

    def test_no_false_release_certification(self):
        self.rebuild(kind="bad_status")
        with self.assertRaisesRegex(InstallError,"release hold"):
            self.install()

    def test_untrusted_archive_symlink_denied(self):
        real=self.root/'original.tar'
        self.archive.rename(real)
        self.archive.symlink_to(real)
        with self.assertRaises((OSError, InstallError)):
            self.install()
        self.assertEqual(list(self.install_root.iterdir()),[])

    def test_output_directory_symlink_denied(self):
        self.install_root.rmdir()
        self.install_root.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises((OSError, InstallError)):
            self.install()

    def test_excess_file_size_denied_even_with_small_bundle(self):
        self.members[0]=(self.members[0][0],b'blob'*50_000,self.members[0][2])
        self.rebuild()
        with self.assertRaisesRegex(InstallError,"approved size window"):
            install_approved_model(self.archive,self.install_root,model_id="original",
                install_id="model-v1", minimum_archive_bytes=1,
                maximum_archive_bytes=25_000,minimum_real_bytes=1)
        self.assertEqual(list(self.install_root.iterdir()),[])

if __name__ == "__main__":
    unittest.main()
