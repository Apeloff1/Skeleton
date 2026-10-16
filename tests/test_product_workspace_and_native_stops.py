"""Regression checks for product navigation and native transformer stop semantics.

These are self-contained guardrails; they do not claim model training or live
backend readiness, and avoid expensive build/test side effects.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from skeleton.ai.runtime.inference.native_transformer import _truncate_at_first_stop


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "app"
CATALOG = ROOT / "frontend" / "src" / "product" / "productCatalog.ts"
PRODUCT = ROOT / "frontend" / "app" / "product.tsx"


def _workspace_routes() -> list[tuple[str, str]]:
    content = CATALOG.read_text(encoding="utf-8")
    section = content.split("export const PRODUCT_WORKSPACES =", 1)[1].split("] as const;", 1)[0]
    return re.findall(r"\{\s*id:\s*'([^']+)'[^}]+href:\s*'([^']+)'", section)


class ProductWorkspaceRouteTests(unittest.TestCase):
    def test_workspace_routes_resolve_to_real_expo_entry_files(self):
        routes = _workspace_routes()
        self.assertGreaterEqual(len(routes), 9)
        self.assertEqual(len({entry[0] for entry in routes}), len(routes))
        for workspace_id, href in routes:
            with self.subTest(workspace=workspace_id):
                self.assertTrue(href.startswith("/"))
                target = APP / href.lstrip("/")
                self.assertTrue(
                    target.with_suffix(".tsx").is_file()
                    or (target / "index.tsx").is_file(),
                    f"missing Expo Router entry for {workspace_id}: {href}",
                )

    def test_canonical_product_home_renders_registry(self):
        source = PRODUCT.read_text(encoding="utf-8")
        self.assertIn("PRODUCT_WORKSPACES.map(", source)
        self.assertIn("router.push(workspace.href as never)", source)
        self.assertIn("product-workspace-", source)

    def test_model_inventory_uses_server_authorized_readiness(self):
        source = (APP / "ai-models.tsx").read_text(encoding="utf-8")
        self.assertIn("getChatReadiness", source)
        self.assertIn("requireAuthenticated", source)
        self.assertNotIn("available: true", source)
        self.assertIn("model.readiness.message", source)


class NativeTransformerStopTests(unittest.TestCase):
    def test_first_matching_stop_in_text_wins_not_first_in_configuration(self):
        result = _truncate_at_first_stop("one END two STOP three", ("STOP", "END"))
        self.assertEqual(result, ("one ", True))

    def test_returns_text_unchanged_without_matching_stops(self):
        self.assertEqual(_truncate_at_first_stop("hello", ("NONE",)), ("hello", False))
        self.assertEqual(_truncate_at_first_stop("hello", ()), ("hello", False))

    def test_stop_at_start_and_unicode(self):
        self.assertEqual(_truncate_at_first_stop("STOPhello", ("STOP",)), ("", True))
        self.assertEqual(_truncate_at_first_stop("αβ✓γ", ("✓",)), ("αβ", True))


if __name__ == "__main__":
    unittest.main()
