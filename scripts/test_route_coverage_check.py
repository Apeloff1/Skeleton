#!/usr/bin/env python3
"""Regression tests for the Expo route registry ↔ filesystem contract."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import route_coverage_check as coverage


class RouteCoverageContractTests(unittest.TestCase):
    def test_registry_covers_current_route_files(self) -> None:
        routes = coverage.parse_registry(coverage.REG_FILE)
        on_disk = coverage.scan_app_files()
        matched: set[str] = set()
        missing: list[str] = []

        for route in routes:
            hit = next(
                (candidate for candidate in coverage.expected_filenames(route["path"]) if candidate in on_disk),
                None,
            )
            if hit is None:
                missing.append(route["path"])
            else:
                matched.add(hit)

        orphan = sorted(
            filename
            for filename in on_disk
            if filename not in matched
            and Path(filename).name not in coverage.INFRA_FILES
            and not filename.endswith(("+not-found.tsx", "+html.tsx", "_layout.tsx"))
        )
        self.assertEqual(missing, [], f"registry routes missing files: {missing}")
        self.assertEqual(orphan, [], f"route files missing registry entries: {orphan}")

    def test_expected_filenames_support_flat_nested_and_dynamic_routes(self) -> None:
        self.assertEqual(coverage.expected_filenames("/creator"), ["creator.tsx", "creator/index.tsx"])
        self.assertEqual(
            coverage.expected_filenames("/settings/appearance"),
            ["settings/appearance.tsx", "settings/appearance/index.tsx"],
        )
        self.assertEqual(
            coverage.expected_filenames("/gate/[stage]"),
            ["gate/[stage].tsx", "gate/[stage]/index.tsx"],
        )

    def test_registry_parser_preserves_heavy_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "routeRegistry.ts"
            registry.write_text(
                "export const ROUTES = [\n"
                "  { path: '/fast', title: 'Fast', category: 'core' },\n"
                "  { path: '/heavy', title: 'Heavy', category: 'build', heavy: true },\n"
                "];\n",
                encoding="utf-8",
            )
            rows = coverage.parse_registry(registry)
        self.assertEqual(rows[0]["heavy"], False)
        self.assertEqual(rows[1]["heavy"], True)


if __name__ == "__main__":
    unittest.main()
