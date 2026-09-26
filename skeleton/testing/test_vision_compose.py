"""Vision → blueprint composition (forge E2E gap: vision-derived graphs)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from skeleton.forge.universal import Forge
from skeleton.forge.vision_compose import (
    FALLBACK_FEATURES,
    FEATURES,
    compose_from_vision,
    describe,
    detect_features,
)
from skeleton.kernel.errors import BlueprintError

HEIST = (
    "Shoot through zombie waves, craft weapons from scrap, escape before the storm "
    "with a sarcastic butler and a score HUD"
)


class TestDetect(unittest.TestCase):
    def test_detects_in_canonical_order_with_provenance(self):
        features, matches = detect_features(HEIST)
        self.assertEqual(
            features,
            ["combat", "crafting", "collapse", "extraction", "companion", "hud"],
        )
        self.assertEqual(matches["combat"], ["shoot", "zombie", "waves"])
        self.assertEqual(matches["companion"], ["butler"])

    def test_negation_is_clause_scoped(self):
        features, _ = detect_features(
            "a cozy farm with no combat, save your harvest, stress-free"
        )
        self.assertEqual(features, ["persistence"])

    def test_false_friends_ignored(self):
        features, _ = detect_features("an unforgettable story you will not forget")
        self.assertEqual(features, [])

    def test_deterministic(self):
        self.assertEqual(detect_features(HEIST), detect_features(HEIST))

    def test_rejects_non_string(self):
        with self.assertRaises(BlueprintError):
            detect_features(None)  # type: ignore[arg-type]

    def test_bounded_input(self):
        features, _ = detect_features(("quiet " * 2000) + "shoot")
        self.assertEqual(features, [])


class TestCompose(unittest.TestCase):
    def test_graph_is_valid_and_wired(self):
        bp, comp = compose_from_vision(Forge(), HEIST)
        self.assertEqual(bp.validate(), [])
        self.assertEqual(
            set(bp.components),
            {"operator", "spawner", "forge", "collapse", "extract", "jeeves", "hud"},
        )
        wires = {(tuple(w["from"]), tuple(w["to"])) for w in comp.to_dict()["wires"]}
        self.assertIn((("spawner", "spawn"), ("collapse", "tick")), wires)
        self.assertIn((("forge", "weapon"), ("hud", "in")), wires)
        self.assertFalse(comp.fallback)
        self.assertEqual(
            bp.components["spawner"].config["triggers"], ["shoot", "zombie", "waves"]
        )

    def test_every_feature_subset_validates(self):
        names = [f.name for f in FEATURES]
        for mask in range(1, 1 << len(names)):
            chosen = [n for i, n in enumerate(names) if mask >> i & 1]
            vision = " ".join(
                next(f for f in FEATURES if f.name == n).stems[0] for n in chosen
            )
            bp, comp = compose_from_vision(Forge(), vision)
            self.assertEqual(comp.features, chosen)
            self.assertEqual(bp.validate(), [], chosen)

    def test_fallback_is_explicit(self):
        bp, comp = compose_from_vision(Forge(), "a quiet poem about rain")
        self.assertTrue(comp.fallback)
        self.assertEqual(set(comp.features), set(FALLBACK_FEATURES))
        self.assertIn("(fallback)", describe(comp.to_dict()))
        self.assertEqual(bp.validate(), [])

    def test_unknown_fallback_rejected(self):
        with self.assertRaises(BlueprintError):
            compose_from_vision(Forge(), "", fallback=("teleport",))

    def test_requires_forge(self):
        with self.assertRaises(BlueprintError):
            compose_from_vision(object(), HEIST)  # type: ignore[arg-type]

    def test_materialises_green_for_godot(self):
        forge = Forge()
        bp, _ = compose_from_vision(forge, HEIST)
        art = forge.materialise(bp, target="godot", repair=True)
        self.assertTrue(art["verification"]["accepted"])
        self.assertEqual(set(art["execution_order"]), set(bp.components))


class TestGameForgeAuto(unittest.TestCase):
    def test_auto_archetype_composes_from_vision(self):
        from skeleton.context.pipeline import GameForgeRun

        payload = GameForgeRun().execute(HEIST, archetype="auto")
        self.assertTrue(payload["succeeded"])
        comp = payload["forge"]["composition"]
        self.assertEqual(comp["features"][:2], ["combat", "crafting"])
        self.assertTrue(payload["forge"]["verification"]["accepted"])

    def test_default_archetype_unchanged(self):
        from skeleton.context.pipeline import GameForgeRun

        payload = GameForgeRun().execute(HEIST)
        self.assertTrue(payload["succeeded"])
        self.assertIsNone(payload["forge"]["composition"])


class TestCockpitArchetype(unittest.TestCase):
    def test_bind_archetype_pins_pipeline(self):
        from skeleton.context.cockpit import Cockpit
        from skeleton.context.pipeline import GameForgeRun

        cockpit = Cockpit()
        out = cockpit.apply("BIND ARCHETYPE auto")
        self.assertEqual(out["result"], {"archetype": "auto", "composed": True})
        self.assertEqual(cockpit.snapshot()["archetype"], "auto")
        payload = GameForgeRun(cockpit=cockpit).execute(HEIST)
        self.assertTrue(payload["succeeded"])
        self.assertIn("combat", payload["forge"]["composition"]["features"])

    def test_explicit_archetype_beats_cockpit_pin(self):
        from skeleton.context.cockpit import Cockpit
        from skeleton.context.pipeline import GameForgeRun

        cockpit = Cockpit()
        cockpit.apply("BIND ARCHETYPE auto")
        payload = GameForgeRun(cockpit=cockpit).execute(HEIST, archetype="extraction")
        self.assertIsNone(payload["forge"]["composition"])

    def test_bind_unknown_archetype_rejected(self):
        from skeleton.context.cockpit import Cockpit, CockpitError

        cockpit = Cockpit()
        with self.assertRaises(CockpitError):
            cockpit.apply("BIND ARCHETYPE teleporter")
        with self.assertRaises(CockpitError):
            cockpit.apply("BIND ARCHETYPE")
        self.assertIsNone(cockpit.archetype)

    def test_compose_preview_is_recorded(self):
        from skeleton.context.cockpit import Cockpit, CockpitError

        cockpit = Cockpit()
        height = cockpit.ledger.height
        out = cockpit.apply(f'COMPOSE "{HEIST}"')
        self.assertTrue(out["result"]["summary"].startswith("6 systems"))
        self.assertEqual(
            cockpit.snapshot()["composition"]["features"], out["result"]["features"]
        )
        self.assertEqual(cockpit.ledger.height, height + 1)
        with self.assertRaises(CockpitError):
            cockpit.apply("COMPOSE")


class TestComposeRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        path = (
            Path(__file__).resolve().parents[2]
            / "backend"
            / "routes"
            / "skeleton_gameforge.py"
        )
        spec = importlib.util.spec_from_file_location("_skeleton_gameforge_route", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        app = FastAPI()
        app.include_router(module.router)
        cls.client = TestClient(app)

    def test_compose_preview(self):
        res = self.client.post("/api/skeleton/compose", json={"vision": HEIST})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("combat", body["features"])
        self.assertTrue(body["summary"].startswith("6 systems"))
        self.assertIn("operator", body["topology"]["components"])

    def test_compose_rejects_oversized_vision(self):
        res = self.client.post("/api/skeleton/compose", json={"vision": "x" * 4001})
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
