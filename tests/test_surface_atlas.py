"""The product shell must be able to open every installed Expo route."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _generator():
    path = ROOT / "scripts" / "generate_surface_atlas.py"
    spec = importlib.util.spec_from_file_location("generate_surface_atlas", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class SurfaceAtlasTests(unittest.TestCase):
    def test_checked_in_atlas_matches_the_app_directory(self) -> None:
        self.assertEqual(_generator().validate_atlas(ROOT), [])

    def test_every_public_route_is_indexed_once(self) -> None:
        generator = _generator()
        routes = generator.collect_routes(ROOT)
        entries = generator.build_entries(ROOT)
        hrefs = [entry["href"] for entry in entries]
        self.assertEqual(hrefs, sorted(hrefs, key=lambda href: (
            next(item["pillar"] for item in entries if item["href"] == href),
            next(str(item["title"]).lower() for item in entries if item["href"] == href),
            href,
        )))
        self.assertCountEqual(hrefs, routes)
        self.assertEqual(len(hrefs), len(set(hrefs)))
        self.assertGreater(len(routes), 100)
        self.assertIn("/", routes)
        self.assertIn("/surfaces", routes)
        self.assertIn("/product", routes)
        self.assertNotIn("/gate/:stage", routes)
        self.assertTrue((ROOT / "frontend" / "app" / "gate" / "[stage].tsx").is_file())

    def test_orphans_are_exactly_the_routes_missing_from_the_catalog(self) -> None:
        generator = _generator()
        linked = generator.catalog_hrefs(ROOT)
        entries = generator.build_entries(ROOT)
        for entry in entries:
            self.assertEqual(entry["orphan"], entry["href"] not in linked)
        for href in ("/forge", "/playable", "/menu", "/hub", "/surfaces", "/command-center"):
            self.assertIn(href, linked)
        orphans = [entry for entry in entries if entry["orphan"]]
        self.assertGreater(len(orphans), 0)
        self.assertTrue(all(entry["href"] not in linked for entry in orphans))

    def test_product_home_searches_the_atlas(self) -> None:
        product = (ROOT / "frontend" / "app" / "product.tsx").read_text(encoding="utf-8")
        self.assertIn("INSTALLED_SURFACES", product)
        self.assertIn("/surfaces", product)
        self.assertIn("matchingSurfaces", product)
        surfaces = (ROOT / "frontend" / "app" / "surfaces.tsx").read_text(encoding="utf-8")
        self.assertIn("ORPHAN_SURFACES", surfaces)
        self.assertIn("No surfaces found", surfaces)


if __name__ == "__main__":
    unittest.main()
