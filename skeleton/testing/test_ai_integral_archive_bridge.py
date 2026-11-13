"""Actual builder -> provenance ledger -> archive -> installer -> sealed GGUF handoff.

No fake 1.9GB payload. Small original fixture exercises the same real codepaths
with explicitly tightened test-only size bounds, never production defaults.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from skeleton.ai.runtime.operational_ai.model.gguf.prepare import prepare_gguf
from skeleton.ai.runtime.operational_ai.model.gguf.service import load_approved_manifest
from skeleton.ai.runtime.operational_ai.model.gguf.assembly import assemble_model
from skeleton.ai.runtime.operational_ai.deployment.install import install_approved_model

BUILDER = Path(__file__).resolve().parents[2] / "scripts" / "build_ai_ecosystem_bundle.py"


def git(repo,*args):
    run=subprocess.run(["git",*args],cwd=repo,capture_output=True,text=True)
    if run.returncode:raise RuntimeError(run.stderr)


class TestRealArchiveBridge(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ai-package-bridge-',dir=Path.home())
        self.root=Path(self.temp.name);self.root.chmod(0o700)
        self.repo=self.root/'repo';self.repo.mkdir(mode=0o700)
        self.payload=self.root/'payload'
        self.installs=self.root/'installed';self.installs.mkdir(mode=0o700)
        self.artifact=self.root/'one-real-bundle.tar'
        self.model=self.root/'source.gguf'
        self.model.write_bytes(b'GGUF'+struct.pack('<IQQ',3,1,1)+b'original model header'+b'\x00'*128)
        self.model.chmod(0o400)
        git(self.repo,'init','-q')
        git(self.repo,'config','user.email','fixture@example.invalid')
        git(self.repo,'config','user.name','fixture')
        for i in range(8):
            path=self.repo/'skeleton/ai'/f'MBW-{i:02d}.py'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(f'# verified source wave {i}\n')
        profile={'schema_version':1,'source_root':'skeleton/ai',
                 'support_files':{},'minimum_archive_bytes':1,
                 'maximum_archive_bytes':5_000_000,'minimum_source_bytes':16,
                 'wave_prefixes':{f'MBW-{i:02d}':[f'skeleton/ai/MBW-{i:02d}.py'] for i in range(8)}}
        for path,data in ((self.repo/'machine/ai_ecosystem_bundle_v1.json',profile),
                          (self.repo/'machine/ai_master_build_sequence.json',{'schema_version':1,
                            'waves':[{'id':f'MBW-{i:02d}', 'hard_dependencies':[f'MBW-{i-1:02d}'] if i else [],
                                      'work_packages':[f'WP-W{i:02d}']} for i in range(8)]})):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(data))
        (self.repo/'scripts').mkdir()
        shutil.copyfile(BUILDER,self.repo/'scripts/build_ai_ecosystem_bundle.py')
        git(self.repo,'add','.')
        git(self.repo,'commit','-qm','offline source fixture')
        self.prepared=prepare_gguf(self.model,self.payload,model_id='original',license='original',
            source='operator:fixture',rights_approved=True,shard_bytes=1_000_000,
            context_ceiling=2048,memory_bytes=128_000_000)
        # Load the exact package-builder source, no reimplementation of its policy.
        spec=importlib.util.spec_from_file_location('skeleton_ai_package_bridge',BUILDER)
        assert spec and spec.loader
        self.builder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.builder)

    def tearDown(self):
        self.model.chmod(0o600)
        self.temp.cleanup()

    def test_builder_output_installs_and_assembles_without_mocks(self):
        record=json.loads((self.payload/'approved_artifacts.json').read_text())
        self.assertEqual(len(record['artifacts']),2)
        self.assertTrue(all(x['destination'].startswith('models/original/') for x in record['artifacts']))
        built=self.builder.build(self.repo,self.payload,'approved_artifacts.json',
                 'machine/ai_ecosystem_bundle_v1.json',self.artifact)
        self.assertEqual(built['status'],'integrity-verified-not-release-certified')
        installed=install_approved_model(self.artifact,self.installs,model_id='original',
            install_id='verified-v1',minimum_archive_bytes=1,maximum_archive_bytes=5_000_000,
            minimum_real_bytes=1)
        self.assertEqual(installed.model_sha256,hashlib.sha256(self.model.read_bytes()).hexdigest())
        manifest=load_approved_manifest(self.installs/'verified-v1')
        with assemble_model(self.installs/'verified-v1',manifest) as sealed:
            self.assertEqual(os.pread(sealed.fd,len(self.model.read_bytes()),0),self.model.read_bytes())

    def test_archive_tampering_holds_output(self):
        self.builder.build(self.repo,self.payload,'approved_artifacts.json',
                 'machine/ai_ecosystem_bundle_v1.json',self.artifact)
        with self.artifact.open('r+b') as out:
            out.seek(512);out.write(b'X')
        with self.assertRaises(Exception):
            install_approved_model(self.artifact,self.installs,model_id='original',
                install_id='bad',minimum_archive_bytes=1,maximum_archive_bytes=5_000_000,
                minimum_real_bytes=1)
        self.assertFalse((self.installs/'bad').exists())

if __name__=='__main__':unittest.main()
