"""No-clobber operator-state and AES key material provision regression suite."""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import unittest
from skeleton.ai.runtime.operational_ai.deployment.bootstrap import provision,ProvisionError
from skeleton.ai.runtime.operational_ai.context.sealed_memory.keys import load_key_file


class TestFirstInstall(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='integral-ai-bootstrap-',dir=Path.home())
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.keys=self.root/'secrets';self.keys.mkdir(mode=0o700)
    def tearDown(self):self.tmp.cleanup()

    def test_private_state_and_key_ready_for_runtime(self):
        result=provision(self.root,'ai-state',self.keys)
        self.assertEqual(result.key_bytes,32)
        self.assertEqual((self.root/'ai-state').stat().st_mode&0o777,0o700)
        self.assertEqual((self.keys/'memory.key').stat().st_mode&0o777,0o600)
        self.assertEqual(len(load_key_file(self.keys/'memory.key').master),32)
        self.assertNotIn(load_key_file(self.keys/'memory.key').master.hex(),str(result))

    def test_existing_state_does_not_create_key(self):
        (self.root/'ai-state').mkdir(mode=0o700)
        with self.assertRaisesRegex(ProvisionError,'already exists'):
            provision(self.root,'ai-state',self.keys)
        self.assertFalse((self.keys/'memory.key').exists())

    def test_existing_key_does_not_create_state(self):
        (self.keys/'memory.key').write_bytes(b'x'*32)
        with self.assertRaisesRegex(ProvisionError,'already exists'):
            provision(self.root,'ai-state',self.keys)
        self.assertFalse((self.root/'ai-state').exists())

    def test_state_symlink_alias_refused(self):
        (self.root/'ai-state').symlink_to(self.keys,target_is_directory=True)
        with self.assertRaisesRegex(ProvisionError,'already exists'):
            provision(self.root,'ai-state',self.keys)
        self.assertFalse((self.keys/'memory.key').exists())

    def test_key_symlink_alias_refused(self):
        (self.keys/'memory.key').symlink_to(self.root/'target')
        with self.assertRaisesRegex(ProvisionError,'already exists'):
            provision(self.root,'ai-state',self.keys)
        self.assertFalse((self.root/'ai-state').exists())

    def test_invalid_state_path_refused(self):
        for value in ('../escape','-dash','a/b','', '..'):
            with self.subTest(value=value),self.assertRaises(ProvisionError):
                provision(self.root,value,self.keys)

    def test_world_writable_parent_refused(self):
        self.keys.chmod(0o777)
        with self.assertRaises(Exception):provision(self.root,'ai-state',self.keys)
        self.assertFalse((self.root/'ai-state').exists())

    def test_second_provision_never_overwrites_secret(self):
        provision(self.root,'ai-state',self.keys)
        original=(self.keys/'memory.key').read_bytes()
        with self.assertRaises(ProvisionError):provision(self.root,'ai-state',self.keys)
        self.assertEqual(original,(self.keys/'memory.key').read_bytes())

if __name__=='__main__':unittest.main()
