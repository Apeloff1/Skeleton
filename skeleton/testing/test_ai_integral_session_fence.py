"""Cross-process native-turn fencing: stale locks, path injection, no shadow files."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from skeleton.ai.runtime.operational_ai.orchestration.custody.session import (
    ProcessSessionFence,SessionFenceError,
)
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation


class TestSessionCustody(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ai-fence-',dir=Path.home())
        self.root=Path(self.temp.name);self.root.chmod(0o700)
    def tearDown(self):self.temp.cleanup()
    def filename(self,session):return self.root/(hashlib.sha256(session.encode()).hexdigest()+'.lock')

    def test_two_open_descriptors_serialize_same_session(self):
        with ProcessSessionFence(self.root) as first,ProcessSessionFence(self.root) as second:
            with first.reserve('s_1'):
                with self.assertRaisesRegex(SessionFenceError,'deadline'):
                    with second.reserve('s_1',deadline_ms=10):pass
            with second.reserve('s_1',deadline_ms=10):pass

    def test_two_different_sessions_can_run_concurrently(self):
        with ProcessSessionFence(self.root) as first,ProcessSessionFence(self.root) as second:
            with first.reserve('s_1'):
                with second.reserve('s_2',deadline_ms=10):pass

    def test_held_lock_blocks_independent_child_process(self):
        code=("from skeleton.ai.runtime.operational_ai.orchestration.custody.session import ProcessSessionFence\n"
              + f"with ProcessSessionFence({str(self.root)!r}) as f:\n"
              + " with f.reserve('s_1',deadline_ms=20):pass\n")
        with ProcessSessionFence(self.root) as parent:
            with parent.reserve('s_1'):
                result=subprocess.run([sys.executable,'-c',code],capture_output=True,
                    text=True,timeout=5)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('deadline',result.stderr)
            result=subprocess.run([sys.executable,'-c',code],capture_output=True,
                text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_owner_only_lock_file(self):
        with ProcessSessionFence(self.root) as fence:
            with fence.reserve('s_1'):pass
        self.assertEqual(self.filename('s_1').stat().st_mode & 0o777,0o600)

    def test_symlink_collision_refused(self):
        target=self.root/'target';target.write_text('untouched')
        self.filename('s_1').symlink_to(target)
        with ProcessSessionFence(self.root) as fence:
            with self.assertRaises(OSError):
                with fence.reserve('s_1'):pass
        self.assertEqual(target.read_text(),'untouched')

    def test_hardlinked_lock_file_refused(self):
        p=self.filename('s_1');p.write_text('owner');p.chmod(0o600)
        os.link(p,self.root/'alias.lock')
        with ProcessSessionFence(self.root) as fence:
            with self.assertRaisesRegex(SessionFenceError,'unique'):
                with fence.reserve('s_1'):pass

    def test_world_readable_lock_file_refused(self):
        p=self.filename('s_1');p.write_text('owner');p.chmod(0o644)
        with ProcessSessionFence(self.root) as fence:
            with self.assertRaisesRegex(SessionFenceError,'private'):
                with fence.reserve('s_1'):pass

    def test_scope_injection_is_refused(self):
        with ProcessSessionFence(self.root) as fence:
            with self.assertRaises(ContractViolation):
                with fence.reserve('../s_1'):pass

    def test_private_directory_required(self):
        self.root.chmod(0o777)
        with self.assertRaises(Exception):ProcessSessionFence(self.root)

    def test_closed_fence_is_refused(self):
        fence=ProcessSessionFence(self.root);fence.close()
        with self.assertRaisesRegex(SessionFenceError,'closed'):
            with fence.reserve('s_1'):pass

if __name__=='__main__':unittest.main()
