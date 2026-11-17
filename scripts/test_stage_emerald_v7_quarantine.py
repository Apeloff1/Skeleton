"""Quarantine staging hostile and synthetic tests, never model release signoff."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_emerald_v7_quarantine as stage

class V7QuarantineTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.source=self.root/"verified-original"
        self.source.mkdir()
        self.output=self.root/"unadopted-quarantine"
        self.forms=[]
        self.models=[]
        for i,name in enumerate(("pathfinder","archivist")):
            payload=(name+"-original-stage-source").encode("ascii")
            file=self.source/(name+".glb")
            file.write_bytes(payload)
            sha=hashlib.sha256(payload).hexdigest()
            entries=[]
            previous=0
            chunks=(payload[:8],payload[8:16],payload[16:20],payload[20:])
            for j,chunk in enumerate(chunks):
                entries.append({
                    "path":f"assets/emerald/evolution-v7/{name}/{name}.glb.part{j+1:03}",
                    "bytes":len(chunk),
                    "sha256":hashlib.sha256(chunk).hexdigest(),
                    "offset":previous,
                })
                previous+=len(chunk)
            self.forms.append({"stage":name,"asset":name+".glb",
                               "bytes":len(payload),"sha256":sha,
                               "parts":entries})
            self.models.append({
                "stage":name,"model_bytes":len(payload),
                "model_sha256":sha,"original_donor_sha256":stage.DONOR,
                "rig_joints":108,"animation_clips":381,
                "tail_root_joint":34,"corrected_clip":"orbit-02",
                "corrected_quaternion_keys":160,
                "release_qualified":False,
                "verified_raw_git_parts":[{
                    "path":part["path"],"bytes":part["bytes"],
                    "sha256":part["sha256"],"git_blob_oid":str(i)*40,
                } for part in entries],
            })
        self.ledger={
            "schema":stage.remote.RECEIPT_SCHEMA,
            "original_donor_sha256":stage.DONOR,
            "remote_repository":"Apeloff1/Skeleton",
            "original_model_count":2,
            "verified_original_git_raw_bytes":229515688,
            "remote_binary_publication_verified":True,
            "full_continuous_collision_qualified":False,
            "real_three_mixer_qualified":False,
            "artist_approved":False,
            "unreal_compiled":False,
            "physical_rtx_verified":False,
            "release_qualified":False,
            "original_model_heads":{
                name:{"branch":stage.publication.target_ref(name),
                      "head":str(i)*40}
                for i,name in enumerate(("pathfinder","archivist"))
            },
            "models":self.models,
        }
        self.write_receipt()

    def write_receipt(self):
        (self.source/stage.SOURCE_RECEIPT).write_text(
            json.dumps(self.ledger),encoding="utf-8")

    def test_exact_original_remote_receipt_custody(self):
        verified=stage.source_receipt(self.source,self.forms)
        self.assertTrue(verified["remote_binary_publication_verified"])
        self.assertFalse(verified["release_qualified"])

    def test_false_remote_claim_refused(self):
        self.ledger["remote_binary_publication_verified"]=False
        self.write_receipt()
        with self.assertRaisesRegex(ValueError,"incomplete or self-contradictory"):
            stage.source_receipt(self.source,self.forms)

    def test_forged_remote_branch_denied(self):
        self.ledger["original_model_heads"]["pathfinder"]["branch"]="refs/heads/main"
        self.write_receipt()
        with self.assertRaisesRegex(ValueError,"incorrect original Git branch"):
            stage.source_receipt(self.source,self.forms)

    def test_rearranged_or_wrong_original_parts_denied(self):
        self.ledger["models"][0]["verified_raw_git_parts"][0]["sha256"]="0"*64
        self.write_receipt()
        with self.assertRaisesRegex(ValueError,"source part receipt"):
            stage.source_receipt(self.source,self.forms)

    def test_extra_or_missing_original_model_denied(self):
        (self.source/"unrequested.glb").write_bytes(b"evil")
        with self.assertRaisesRegex(ValueError,"unknown, linked"):
            stage.source_receipt(self.source,self.forms)

    def test_symlink_into_original_source_is_denied(self):
        file=self.source/"pathfinder.glb"
        file.unlink()
        try:
            file.symlink_to(self.source/"archivist.glb")
        except OSError:
            self.skipTest("symlink not supported")
        with self.assertRaisesRegex(ValueError,"unknown, linked"):
            stage.source_receipt(self.source,self.forms)

    def test_verified_byte_copy_and_same_size_mutation_denial(self):
        form=self.forms[0]
        output=self.root/"pathfinder.glb"
        result=stage.exact_copy(self.source/"pathfinder.glb",output,
                                form["bytes"],form["sha256"])
        self.assertEqual(result["sha256"],form["sha256"])
        self.assertEqual(output.read_bytes(),
                         (self.source/"pathfinder.glb").read_bytes())
        output.unlink()
        tampered=bytearray((self.source/"pathfinder.glb").read_bytes())
        tampered[0]^=1
        (self.source/"pathfinder.glb").write_bytes(tampered)
        with self.assertRaisesRegex(ValueError,"SHA-256 differs"):
            stage.exact_copy(self.source/"pathfinder.glb",output,
                             form["bytes"],form["sha256"])
        self.assertFalse(output.exists())

    def test_original_worktree_is_never_install_destination(self):
        with self.assertRaisesRegex(ValueError,"application source"):
            stage.outside_worktree(stage.ROOT/"frontend/public/emerald/v1")
        with self.assertRaisesRegex(ValueError,"application source"):
            stage.outside_worktree(stage.ROOT/"Models")

    def test_existing_destination_is_untouched(self):
        self.output.mkdir()
        (self.output/"keep.txt").write_text("preserve")
        with self.assertRaisesRegex(ValueError,"fresh separate"):
            stage.install_quarantine(self.source,self.output)
        self.assertEqual((self.output/"keep.txt").read_text(),"preserve")

    def test_synthetic_quarantine_marks_every_app_adoption_hold(self):
        # Test orchestration with deliberately tiny synthetic files; the
        # production CLI cannot change the immutable manifest model hashes.
        def pretend_model_check(path,form):
            self.assertEqual(path.read_bytes(),
                             (self.source/form["asset"]).read_bytes())
            return {"model_sha256":form["sha256"],"release_qualified":False}
        with patch.object(stage.publication,"load",return_value=(self.forms,b"synthetic")),\
             patch.object(stage.remote,"verify_model_shape",side_effect=pretend_model_check):
            outcome=stage.install_quarantine(self.source,self.output)
        self.assertTrue((self.output/stage.STAGING_RECEIPT).exists())
        self.assertEqual(len(list(self.output.iterdir())),3)
        self.assertEqual(outcome["original_model_count"],2)
        self.assertFalse(outcome["approved_for_runtime"])
        self.assertFalse(outcome["frontend_public_asset_installed"])
        self.assertFalse(outcome["native_original_model_replaced"])
        self.assertFalse(outcome["remote_publication_revalidated_by_this_step"])
        self.assertFalse(outcome["physical_rtx_verified"])
        self.assertFalse(outcome["release_qualified"])
        self.assertFalse((self.root/".unadopted-quarantine.quarantine.lock").exists())

    def test_stale_original_source_cannot_pass_without_two_models(self):
        self.ledger["models"].pop()
        self.write_receipt()
        with self.assertRaisesRegex(ValueError,"missing original remote revisions"):
            stage.source_receipt(self.source,self.forms)

if __name__=="__main__":
    unittest.main()
