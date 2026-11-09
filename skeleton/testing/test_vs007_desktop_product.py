from __future__ import annotations
import hashlib
import unittest
from skeleton.eval.vertical_suite import DesktopAcceptanceRun, DesktopArtifactReceipt, DesktopProductFixture, DesktopRollbackEvidence, VerticalSuiteError

class VS007DesktopProductTests(unittest.TestCase):
    def _run(self, rollback_matches=True):
        before=hashlib.sha256(b"state-v1").hexdigest()
        return DesktopAcceptanceRun(
            environment_id="clean-win-x64",
            install_ref="install:signed-msi",
            artifact=DesktopArtifactReceipt(
                release_digest=hashlib.sha256(b"release").hexdigest(),
                signed_release_ref="signature:release",
                governed_operation_ref="operation:vs001-local",
                artifact_digest=hashlib.sha256(b"artifact").hexdigest(),
            ),
            restart_ref="restart:ok",
            update_ref="update:interrupted-resumed",
            migration_ref="migration:v1-v2",
            rollback=DesktopRollbackEvidence(
                before_state_digest=before,
                migrated_state_digest=hashlib.sha256(b"state-v2").hexdigest(),
                rollback_state_digest=before if rollback_matches else hashlib.sha256(b"bad").hexdigest(),
                update_interruption_ref="drill:update-interruption",
            ),
        )

    def test_clean_install_operation_update_migration_and_rollback(self):
        receipt=DesktopProductFixture().accept(self._run())
        self.assertEqual(len(receipt),64)

    def test_rollback_must_restore_authoritative_state(self):
        with self.assertRaisesRegex(VerticalSuiteError,"restore authoritative state"):
            DesktopProductFixture().accept(self._run(False))

if __name__=="__main__": unittest.main()
