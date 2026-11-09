"""Guard the single product UI route catalog against dead links."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_product_surfaces import ROOT, SURFACES, module_exists, page_exists, validate


class ProductSurfaceNavigationTests(unittest.TestCase):
    def test_checked_in_catalog_and_home_routes_resolve(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_route_file_and_nested_index(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / "frontend" / "app"
            app.mkdir(parents=True)
            (app / "studio.tsx").write_text("export default () => null;", encoding="utf-8")
            nested = app / "settings"
            nested.mkdir()
            (nested / "index.tsx").write_text("export default () => null;", encoding="utf-8")
            self.assertTrue(page_exists(root, "/studio"))
            self.assertTrue(page_exists(root, "/settings"))
            self.assertFalse(page_exists(root, "/missing"))
            self.assertFalse(page_exists(root, "/../unsafe"))

    def test_local_module_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "ui.tsx"
            source.write_text("", encoding="utf-8")
            (root / "utils.ts").write_text("", encoding="utf-8")
            self.assertTrue(module_exists(source, "./utils"))
            self.assertFalse(module_exists(source, "./missing"))

    def test_catalog_and_core_import_validation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for relpath in SURFACES:
                path = root / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            catalog = root / "frontend/src/product/productCatalog.ts"
            catalog.write_text(
                "export const PRODUCT_HOME_SHORTCUT_IDS = ['studio.home'] as const;\n"
                "{ navigationId: 'studio.home', href: '/studio' }\n",
                encoding="utf-8",
            )
            route = root / "frontend/app/studio.tsx"
            route.write_text("export default () => null;", encoding="utf-8")
            self.assertEqual(validate(root), [])
            route.unlink()
            self.assertTrue(any("missing Expo route" in e for e in validate(root)))
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace("studio.home'] as", "orphan.home'] as"),
                encoding="utf-8",
            )
            self.assertTrue(any("orphaned home shortcut" in e for e in validate(root)))


if __name__ == "__main__":
    unittest.main()
