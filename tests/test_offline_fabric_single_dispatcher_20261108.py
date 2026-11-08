"""The offline product compatibility API must be one canonical dispatcher."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.production_fabric.product.api import LocalAPI as CompatibilityAPI
from skeleton.ai.runtime.production_fabric.product.dispatcher import LocalAPI as CanonicalAPI
from skeleton.ai.runtime.production_fabric.product.cli import LocalAPI as CLIAPI


class SingleOfflineDispatcherTests(unittest.TestCase):
    def test_identity_is_shared_not_a_second_implementation(self):
        self.assertIs(CompatibilityAPI, CanonicalAPI)
        self.assertIs(CLIAPI, CanonicalAPI)

    def test_dispatch_authority_is_owned_by_local_product_dispatcher(self):
        self.assertEqual(CanonicalAPI.__module__,
                         "skeleton.ai.runtime.production_fabric.product.dispatcher")

    def test_cli_rejects_oversized_world_before_opening_sqlite(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from skeleton.ai.runtime.production_fabric.product import cli

        with TemporaryDirectory() as directory:
            world = Path(directory) / "world.json"
            world.write_bytes(b" " * 65)
            with patch.object(cli, "MAX_JSON_BYTES", 64), patch.object(cli, "Journal") as journal:
                error = io.StringIO()
                with redirect_stderr(error):
                    code = cli.main(["--world", str(world), "--db",
                                     str(Path(directory) / "store.db"), "--request", "{}"])
            self.assertEqual(code, 1)
            self.assertIn("world input exceeds byte limit", error.getvalue())
            journal.assert_not_called()

    def test_cli_closes_sqlite_when_world_validation_fails(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from skeleton.ai.runtime.production_fabric.product import cli

        with TemporaryDirectory() as directory:
            world = Path(directory) / "world.json"
            world.write_bytes(b"{}")
            with patch.object(cli, "Journal") as journal, \
                 patch.object(cli, "ProductionEngine", side_effect=cli.FabricError("world denied")):
                with redirect_stderr(io.StringIO()):
                    code = cli.main(["--world", str(world), "--db",
                                     str(Path(directory) / "store.db"), "--request", "{}"])
            self.assertEqual(code, 1)
            journal.return_value.close.assert_called_once_with()

    def test_cli_closes_sqlite_when_dispatch_fails(self):
        import io
        from contextlib import redirect_stderr
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from skeleton.ai.runtime.production_fabric.product import cli

        with TemporaryDirectory() as directory:
            world = Path(directory) / "world.json"
            world.write_bytes(b"{}")
            with patch.object(cli, "Journal") as journal, \
                 patch.object(cli, "ProductionEngine"), \
                 patch.object(cli, "LocalAPI") as dispatcher:
                dispatcher.return_value.json.side_effect = cli.FabricError("request denied")
                with redirect_stderr(io.StringIO()):
                    code = cli.main(["--world", str(world), "--db",
                                     str(Path(directory) / "store.db"), "--request", "{}"])
            self.assertEqual(code, 1)
            journal.return_value.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
