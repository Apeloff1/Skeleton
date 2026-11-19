"""Every unimported Jeeves studio module runs inside a sealed build."""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _namespace(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is not None and getattr(module, "__file__", None):
        raise RuntimeError(f"{name} was imported as a regular package; refusing to execute its __init__")
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]
    module.__package__ = name


_namespace("skeleton", ROOT / "skeleton")
_namespace("skeleton.jeeves", ROOT / "skeleton" / "jeeves")
_namespace("skeleton.jeeves.studio", ROOT / "skeleton" / "jeeves" / "studio")


def _load(name: str):
    return importlib.import_module(f"skeleton.jeeves.studio.{name}")


class StudioCatalogTests(unittest.TestCase):
    def test_orphans_are_the_unimported_siblings(self) -> None:
        catalog = _load("studio_catalog")
        names = catalog.orphan_names()
        self.assertGreaterEqual(len(names), 514)
        self.assertNotIn("integrated_studio", names)
        self.assertIn("auction_stub", names)
        self.assertIn("cloud_save", names)

    def test_run_orphans_executes_every_module(self) -> None:
        catalog = _load("studio_catalog")
        result = catalog.run_orphans({
            "brief": "Build a sealed ash tunnel with a boss",
            "era": "ash",
            "optical": 0.95,
            "fidelity": 0.96,
            "mode": "2.9D",
            "rooms": 7,
        })
        self.assertTrue(result["ok"])
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["ran"], result["count"])
        self.assertEqual(result["reason"], "ok")
        self.assertEqual(result["schema"], "skeleton.studio.catalog.v1")
        self.assertGreaterEqual(result["count"], 514)

    def test_auction_refuses_bad_lots_and_freezes_after_close(self) -> None:
        auction = _load("auction_stub").AuctionStub()
        self.assertFalse(auction.list("", 10)["ok"])
        self.assertFalse(auction.list("relic", -1)["ok"])
        listed = auction.list("relic", 10)
        self.assertTrue(listed["ok"])
        bid = auction.bid("relic", 12, "ada")
        self.assertTrue(bid["ok"])
        self.assertEqual(bid["bidder"], "ada")
        closed = auction.close("relic")
        self.assertTrue(closed["ok"])
        self.assertEqual(closed["bidder"], "ada")
        self.assertFalse(auction.bid("relic", 20, "bea")["ok"])
        self.assertFalse(auction.bid("missing", 20, "bea")["ok"])

    def test_cloud_save_stores_only_real_digests(self) -> None:
        save = _load("cloud_save").CloudSave()
        rejected = save.push("abc", "slot")
        self.assertFalse(rejected["ok"])
        self.assertIsNone(rejected["digest"])
        self.assertIsNot(rejected.get("synced"), True)
        digest = "ab" * 32
        stored = save.push(digest, "slot")
        self.assertTrue(stored["ok"])
        self.assertEqual(stored["digest"], digest)
        self.assertTrue(stored["synced"])
        pulled = save.pull("slot")
        self.assertTrue(pulled["ok"])
        self.assertEqual(pulled["digest"], digest)
        missing = save.pull("other")
        self.assertFalse(missing["ok"])
        self.assertIsNone(missing["digest"])

    def test_shader_and_world_emitter_refuse_bad_input(self) -> None:
        compiler = _load("shader_compiler").ShaderCompiler()
        self.assertFalse(compiler.compile("ash", "nope", 0.95)["ok"])
        compiled = compiler.compile("ash", "2.9D", 0.95)
        self.assertTrue(compiled["ok"])
        self.assertIn("shader_type canvas_item;", compiled["source"])
        emitter = _load("godot_world_emitter").GodotWorldEmitter()
        self.assertFalse(emitter.emit("not-a-world")["ok"])
        emitted = emitter.emit({"rooms": [{"id": 1, "biome": "ash"}]})
        self.assertTrue(emitted["ok"])
        self.assertIn("Room_1", emitted["world.tscn"])
        self.assertEqual(emitted["room_count"], 1)

    def test_tilemap_and_ratchet_do_not_crash_on_partial_input(self) -> None:
        level = _load("level_generator").LevelGenerator()
        self.assertEqual(
            level.to_godot_tilemap({}),
            "# TileMap data v2\n# reason: missing_tiles\n",
        )
        rendered = level.to_godot_tilemap({"tiles": [[0, 1], [2, 0]]})
        self.assertIn("1,0,1", rendered)
        self.assertIn("0,1,2", rendered)
        dev = _load("ai_driven_dev").AIDrivenDev()
        self.assertTrue(callable(dev.ratchet))
        stepped = dev.step(0.95, 0.96)
        self.assertEqual(dev.high_water, 0.96)
        self.assertEqual(stepped["ratchet"], 0.96)

    def test_pipeline_seals_with_the_orphan_catalog(self) -> None:
        studio = _load("integrated_studio").IntegratedStudio()
        result = studio.run_pipeline("Build a sealed ash tunnel with a boss and a reward")
        self.assertTrue(result["sealed"], result.get("reason"))
        self.assertGreaterEqual(result["modules"]["count"], 514)
        self.assertTrue(result["modules"]["ok"])
        self.assertGreaterEqual(studio.status()["modules"], 514)


if __name__ == "__main__":
    unittest.main()
