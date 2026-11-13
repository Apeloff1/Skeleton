"""Fail-closed local AI principal and model custody (no inferred migration)."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from skeleton.ai.runtime.operational_ai.deployment.boot.identity import (
    PrincipalBinding, StateIdentityError, establish_binding, inspect_binding,
)
from skeleton.ai.runtime.operational_ai.deployment.boot.readiness import (
    inspect_readiness,
)
from skeleton.ai.runtime.operational_ai.deployment.boot.cli import main as boot_main

A = 'a' * 64
B = 'b' * 64


class TestAIPrincipalCustody(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix='ai-identity-', dir=Path.home())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.identity = PrincipalBinding('tenant_1', 'operator', A, B)
        self.file = self.root / 'state.identity.json'

    def test_exact_first_binding_survives_restart(self):
        first = establish_binding(self.root, self.identity)
        second = inspect_binding(self.root, self.identity)
        self.assertEqual(first, second)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('operator', json.dumps(first))

    def test_idempotent_bind_does_not_rewrite_file(self):
        establish_binding(self.root, self.identity)
        before = self.file.stat().st_mtime_ns
        establish_binding(self.root, self.identity)
        self.assertEqual(before, self.file.stat().st_mtime_ns)

    def test_read_only_check_never_creates_binding(self):
        with self.assertRaisesRegex(StateIdentityError, 'no principal binding'):
            inspect_binding(self.root, self.identity)
        self.assertFalse(self.file.exists())

    def test_tenant_cannot_reuse_same_store(self):
        establish_binding(self.root, self.identity)
        other = PrincipalBinding('tenant_2', 'operator', A, B)
        with self.assertRaisesRegex(StateIdentityError, 'mismatch'):
            inspect_binding(self.root, other)

    def test_user_cannot_reuse_same_store(self):
        establish_binding(self.root, self.identity)
        other = PrincipalBinding('tenant_1', 'other', A, B)
        with self.assertRaisesRegex(StateIdentityError, 'another identity'):
            establish_binding(self.root, other)

    def test_model_rotation_requires_new_state(self):
        establish_binding(self.root, self.identity)
        other = PrincipalBinding('tenant_1', 'operator', B, B)
        with self.assertRaises(StateIdentityError):
            inspect_binding(self.root, other)

    def test_tokenizer_rotation_requires_new_state(self):
        establish_binding(self.root, self.identity)
        other = PrincipalBinding('tenant_1', 'operator', A, A)
        with self.assertRaises(StateIdentityError):
            inspect_binding(self.root, other)

    def test_noncanonical_names_rejected(self):
        for value in ('../x','a/b','','bad name','é','a\0b','x'*129):
            with self.subTest(value=value), self.assertRaises(StateIdentityError):
                PrincipalBinding(value,'operator',A,B)

    def test_incomplete_digests_rejected(self):
        for value in ('0'*63,'Z'*64,'','f'*65):
            with self.subTest(value=value), self.assertRaises(StateIdentityError):
                PrincipalBinding('local','operator',value,B)

    def test_existing_chat_is_never_adopted(self):
        (self.root/'chat.sqlite').write_bytes(b'private conversation')
        with self.assertRaisesRegex(StateIdentityError,'migration'):
            establish_binding(self.root, self.identity)
        self.assertFalse(self.file.exists())

    def test_existing_memory_is_never_adopted(self):
        (self.root/'memory.sqlite').write_bytes(b'private memory')
        with self.assertRaisesRegex(StateIdentityError,'migration'):
            establish_binding(self.root, self.identity)

    def test_existing_session_locks_are_never_adopted(self):
        (self.root/'session_locks').mkdir(mode=0o700)
        with self.assertRaisesRegex(StateIdentityError,'migration'):
            establish_binding(self.root, self.identity)

    def test_symlink_collision_cannot_be_opened_or_replaced(self):
        external = self.root/'outside'
        external.write_bytes(b'secret')
        self.file.symlink_to(external)
        with self.assertRaises(OSError):
            establish_binding(self.root, self.identity)
        self.assertEqual(external.read_bytes(),b'secret')

    def test_hardlink_collision_refused(self):
        establish_binding(self.root, self.identity)
        os.link(self.file, self.root/'alias')
        with self.assertRaisesRegex(StateIdentityError,'unique'):
            inspect_binding(self.root, self.identity)

    def test_world_readable_binding_refused(self):
        establish_binding(self.root, self.identity)
        self.file.chmod(0o644)
        with self.assertRaisesRegex(StateIdentityError,'private'):
            inspect_binding(self.root, self.identity)

    def test_world_readable_root_refused(self):
        self.root.chmod(0o755)
        with self.assertRaises(StateIdentityError):
            establish_binding(self.root, self.identity)

    def test_mutated_checksum_refused(self):
        establish_binding(self.root, self.identity)
        record = json.loads(self.file.read_text())
        record['user'] = 'attacker'
        self.file.write_text(json.dumps(record))
        with self.assertRaisesRegex(StateIdentityError,'checksum'):
            inspect_binding(self.root, self.identity)

    def test_noncanonical_json_refused(self):
        establish_binding(self.root, self.identity)
        record = json.loads(self.file.read_text())
        self.file.write_text(json.dumps(record, indent=2))
        with self.assertRaisesRegex(StateIdentityError,'canonical'):
            inspect_binding(self.root, self.identity)

    def test_duplicate_json_key_refused(self):
        establish_binding(self.root, self.identity)
        raw = self.file.read_text()
        self.file.write_text(raw.replace('"tenant":', '"tenant":"fake","tenant":'))
        with self.assertRaisesRegex(StateIdentityError,'duplicate'):
            inspect_binding(self.root, self.identity)

    def test_partial_published_file_remains_blocking(self):
        self.file.write_bytes(b'{"incomplete":')
        self.file.chmod(0o600)
        with self.assertRaises(StateIdentityError):
            establish_binding(self.root, self.identity)
        self.assertEqual(self.file.read_bytes(),b'{"incomplete":')

    def test_two_competing_startups_agree(self):
        outcomes = []
        def worker():
            try:
                outcomes.append(establish_binding(self.root,self.identity)['status'])
            except Exception as exc:
                outcomes.append(type(exc).__name__)
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertTrue(all(x in ('principal-and-model-bound','StateIdentityError') for x in outcomes))
        self.assertEqual(inspect_binding(self.root,self.identity)['status'],'principal-and-model-bound')

    def test_readiness_does_not_claim_native_model_test(self):
        establish_binding(self.root,PrincipalBinding('tenant_1','operator',A,A))
        model=SimpleNamespace(model_sha256=A,content_verified=True)
        with (patch('skeleton.ai.runtime.operational_ai.deployment.boot.readiness.inspect_installed_model',return_value=model),
              patch('skeleton.ai.runtime.operational_ai.deployment.boot.readiness.load_approved_manifest',return_value=model),
              patch('skeleton.ai.runtime.operational_ai.deployment.boot.readiness.load_key_file',return_value=object()),
              patch('skeleton.ai.runtime.operational_ai.deployment.boot.readiness.importlib.util.find_spec',return_value=None)):
            result=inspect_readiness(self.root,self.root,self.root/'key',tenant='tenant_1',user='operator')
        self.assertFalse(result.local_backend_importable)
        self.assertFalse(result.eligible_for_live_inference_attempt)
        self.assertFalse(result.release_certified)

    def test_cli_bind_requires_explicit_approval(self):
        with patch('skeleton.ai.runtime.operational_ai.deployment.boot.cli.inspect_installed_model',
                   return_value=SimpleNamespace(model_sha256=A)):
            result=boot_main(['bind','--model-root',str(self.root),
                '--state-dir',str(self.root),'--tenant','tenant_1','--user','operator'])
        self.assertEqual(result,2)
        self.assertFalse(self.file.exists())

    def test_binding_refuses_existing_sidecar(self):
        (self.root/'chat.sqlite-wal').write_bytes(b'old context')
        with self.assertRaisesRegex(StateIdentityError,'migration'):
            establish_binding(self.root,self.identity)


if __name__=='__main__':
    unittest.main()
