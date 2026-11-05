"""Adversarial native-process memory pressure admission before durable leases."""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from skeleton.ai.runtime.operational_ai.model.isolation.contracts import IsolationFailure
from skeleton.ai.runtime.operational_ai.model.isolation.resource_gate import (
    Headroom,parse_meminfo,parse_cgroup_limits,read_linux_headroom,_cgroup_directory,
)


class PressureAdmissionTests(unittest.TestCase):
    def test_host_available_memory(self):
        self.assertEqual(parse_meminfo('MemTotal: 2048 kB\nMemAvailable: 1024 kB\n'),1048576)

    def test_missing_host_memory_holds(self):
        with self.assertRaises(IsolationFailure):parse_meminfo('MemFree: 123 kB')

    def test_duplicated_or_malformed_host_memory_holds(self):
        for value in ('MemAvailable: -1 kB','MemAvailable: nope kB',
                      'MemAvailable: 999999999999999999999999 kB'):
            with self.subTest(value=value),self.assertRaises(IsolationFailure):parse_meminfo(value)

    def test_explicit_cgroup_limit(self):
        self.assertEqual(parse_cgroup_limits('500000000','200000000'),300000000)

    def test_unlimited_cgroup_not_conflated_with_zero(self):
        self.assertIsNone(parse_cgroup_limits('max','200000000'))

    def test_overlimit_cgroup_must_hold(self):
        with self.assertRaises(IsolationFailure):parse_cgroup_limits('100','200')

    def test_cgroup_invalid_counter_fails_closed(self):
        for value in ('-1','inf','0.5','18446744073709551616'):
            with self.subTest(value=value),self.assertRaises(IsolationFailure):parse_cgroup_limits(value,'200')

    def test_cgroup_traversal_refused(self):
        with self.assertRaises(IsolationFailure):
            _cgroup_directory(Path('/tmp/cgroups'),'0::/a/../b')

    def test_cgroup_escaped_backslash_refused(self):
        with self.assertRaises(IsolationFailure):
            _cgroup_directory(Path('/tmp/cgroups'),r'0::/a\b')

    def test_multiple_v2_controllers_held(self):
        with self.assertRaises(IsolationFailure):
            _cgroup_directory(Path('/tmp/cgroups'),'0::/a\n0::/b')

    def create_fixture(self, *,available=400000,maximum='500000000',current='200000000'):
        ctx=tempfile.TemporaryDirectory();self.addCleanup(ctx.cleanup)
        root=Path(ctx.name)
        (root/'meminfo').write_text(f'MemAvailable: {available} kB\n')
        (root/'cgroup').write_text('0::/child\n')
        (root/'sys'/'child').mkdir(parents=True)
        (root/'sys'/'child'/'memory.max').write_text(maximum)
        (root/'sys'/'child'/'memory.current').write_text(current)
        return root

    def check(self,root,bytes_needed):
        return read_linux_headroom(bytes_needed,proc_meminfo=root/'meminfo',
            proc_cgroup=root/'cgroup',cgroup_root=root/'sys')

    def test_host_cgroup_minimum(self):
        root=self.create_fixture()
        proof=self.check(root,128*1024*1024)
        self.assertEqual(proof.effective_available_bytes,300000000)
        self.assertTrue(proof.admitted)

    def test_low_cgroup_headroom_rejects(self):
        root=self.create_fixture(maximum='250000000',current='200000000')
        self.assertFalse(self.check(root,128*1024*1024).admitted)

    def test_low_host_headroom_rejects(self):
        root=self.create_fixture(available=20000)
        self.assertFalse(self.check(root,128*1024*1024).admitted)

    def test_incomplete_cgroup_files_refused(self):
        root=self.create_fixture()
        (root/'sys'/'child'/'memory.current').unlink()
        with self.assertRaises(IsolationFailure):self.check(root,128*1024*1024)

    def test_malformed_cgroup_current_refused(self):
        root=self.create_fixture(current='x')
        with self.assertRaises(IsolationFailure):self.check(root,128*1024*1024)

    def test_false_bool_reserve_refused(self):
        root=self.create_fixture()
        with self.assertRaises(IsolationFailure):self.check(root,True)

    def test_explicit_pressure_status_not_certification(self):
        p=Headroom(500000000,100000000,100000000,128*1024*1024)
        self.assertFalse(p.admitted)
        self.assertIn('not-oom-certification',p.to_record()['status'])

    def test_isolated_backend_rejects_pressure_before_reservation(self):
        from skeleton.testing.test_ai_isolated_spine_integration import IsolatedSpineIntegrationTests
        case=IsolatedSpineIntegrationTests('test_roundtrip_commits_atomic_sqlite_event_and_outbox')
        case.setUp()
        try:
            backend,spine=case.open()
            spine.create('s1')
            with patch('skeleton.ai.runtime.operational_ai.model.isolation.client.require_headroom',
                       side_effect=IsolationFailure('simulated memory pressure')):
                with self.assertRaises(IsolationFailure):spine.turn('s1','r1','Hello')
            self.assertEqual(case.count('requests'),0)
            self.assertEqual(backend.health()['requests_completed'],0)
        finally:
            case.doCleanups()


if __name__ == '__main__':unittest.main()
