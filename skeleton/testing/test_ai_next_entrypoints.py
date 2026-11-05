"""Neither recovery nor alternative native JSON CLI may bypass AI state custody."""
from __future__ import annotations

from argparse import Namespace
from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import (
    PrincipalBinding, establish_binding,
)
from skeleton.ai.runtime.operational_ai.deployment.install.cli import main as install_main
from skeleton.ai.runtime.operational_ai.transport.cli import (
    build_service, main as native_main,
)

A='a'*64


class TestAlternateOperatorSurfaces(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ai-entrypoint-',dir=Path.home())
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.root.chmod(0o700)
        self.state=self.root/'private_state'
        self.state.mkdir(mode=0o700)
        self.other=self.root/'other_state'
        self.other.mkdir(mode=0o700)

    def recover(self,tenant='local',user='operator',*,dry_run=True):
        args=['reconcile-audit','--model-root',str(self.root),
              '--state-dir',str(self.state),'--session','s1',
              '--tenant',tenant,'--user',user]
        args+=['--dry-run'] if dry_run else ['--approve']
        with patch('skeleton.ai.runtime.operational_ai.deployment.install.cli.inspect_installed_model',
                   return_value=SimpleNamespace(model_sha256=A)):
            with redirect_stderr(io.StringIO()) as errors:
                result=install_main(args)
        return result,errors.getvalue()

    def test_unbound_recovery_dry_run_refused_without_db_creation(self):
        result,diagnostic=self.recover()
        self.assertEqual(result,2)
        self.assertIn('StateIdentityError',diagnostic)
        self.assertFalse((self.state/'chat.sqlite').exists())
        self.assertFalse((self.state/'audit.sqlite').exists())

    def test_recovery_wrong_tenant_refused(self):
        establish_binding(self.state,PrincipalBinding('local','operator',A,A))
        result,diagnostic=self.recover('another','operator')
        self.assertEqual(result,2)
        self.assertIn('StateIdentityError',diagnostic)
        self.assertFalse((self.state/'chat.sqlite').exists())

    def test_recovery_wrong_user_refused(self):
        establish_binding(self.state,PrincipalBinding('local','operator',A,A))
        result,diagnostic=self.recover('local','another')
        self.assertEqual(result,2)
        self.assertIn('StateIdentityError',diagnostic)

    def test_recovery_wrong_model_refused(self):
        establish_binding(self.state,PrincipalBinding('local','operator','b'*64,A))
        result,diagnostic=self.recover()
        self.assertEqual(result,2)
        self.assertIn('StateIdentityError',diagnostic)

    def test_recovery_checks_identity_before_any_sqlite_open(self):
        establish_binding(self.state,PrincipalBinding('local','operator',A,A))
        with patch('skeleton.ai.runtime.operational_ai.deployment.install.cli.inspect_installed_model',
                   return_value=SimpleNamespace(model_sha256=A)):
            with patch('skeleton.ai.runtime.operational_ai.deployment.install.cli.ExitStack',
                       side_effect=RuntimeError('DB opened')):
                with redirect_stderr(io.StringIO()) as errors:
                    result=install_main(['reconcile-audit','--model-root',str(self.root),
                        '--state-dir',str(self.state),'--session','s1',
                        '--tenant','another','--user','operator','--dry-run'])
        self.assertEqual(result,2)
        self.assertIn('StateIdentityError',errors.getvalue())
        self.assertNotIn('DB opened',errors.getvalue())

    def test_generic_native_cli_refuses_scattered_database_paths(self):
        args=Namespace(database=self.state/'chat.sqlite',
                       memory_db=self.other/'memory.sqlite',
                       journal_db=self.state/'audit.sqlite')
        with self.assertRaisesRegex(ContractViolation,'share one private'):
            from contextlib import ExitStack
            with ExitStack() as stack:build_service(args,stack)

    def test_generic_native_cli_refuses_world_accessible_root(self):
        self.state.chmod(0o755)
        args=Namespace(database=self.state/'chat.sqlite',
                       memory_db=self.state/'memory.sqlite',
                       journal_db=self.state/'audit.sqlite')
        with self.assertRaises(ContractViolation):
            from contextlib import ExitStack
            with ExitStack() as stack:build_service(args,stack)

    def test_generic_native_cli_requires_bearer_before_any_model_load(self):
        with patch('skeleton.ai.runtime.operational_ai.transport.cli.build_service',
                   side_effect=RuntimeError('incorrectly loaded model')) as entry:
            with patch.dict('os.environ',{'SKELETON_LOCAL_AI_BEARER':''}):
                with redirect_stderr(io.StringIO()) as errors:
                    code=native_main(['--checkpoint',str(self.root/'missing.json'),
                        '--sha256',A,'--license','operator-approved',
                        '--database',str(self.state/'chat.sqlite'),
                        '--memory-db',str(self.state/'memory.sqlite'),
                        '--journal-db',str(self.state/'audit.sqlite'),'--serve'])
        self.assertEqual(code,2)
        self.assertIn('InvalidBearerSecret',errors.getvalue())
        entry.assert_not_called()


if __name__ == '__main__':unittest.main()
