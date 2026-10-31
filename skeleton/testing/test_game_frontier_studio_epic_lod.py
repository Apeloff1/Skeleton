"""Measured Godot visual-world LOD quotas: every Epic layer remains visible.

Tests assert actual source data, bounded native MultiMesh instances, hash
lineage, and deterministic broad spatial coverage. Collision and native
controller performance retain separate Godot release qualification.
"""
from __future__ import annotations

from dataclasses import replace
import json
import unittest

from skeleton.forge.game_frontier_studio import StudioError
from skeleton.forge.game_frontier_studio_document import create_authoring_project
from skeleton.forge.game_frontier_studio_epic_lod import (
    allocate_visual_budgets, sample_visual_layer, planned_native_visual_layers,
)
from skeleton.forge.game_frontier_studio_terrain_runtime import (
    add_studio_native_terrain, _SCENE, _SCRIPT, _DATA,
)


def source_worlds(width=64, height=64, count=8):
    p = create_authoring_project("native_epic_lod", width=width, height=height)
    ground = p.layers[0]
    return replace(p, layers=tuple(replace(
        ground, layer_id="epic_layer_"+str(index),
        elevation_m=10.*index,
    ) for index in range(count)))


def original_godot_files():
    return {_SCENE: (
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://game/frontier/expedition.gd" id="1"]\n'
        '[node name="Expedition" type="Node3D"]\n'
        'script = ExtResource("1")\n'
    )}


class EpicMultilayerNativeLODTests(unittest.TestCase):
    def test_all_eight_dense_layers_share_exact_native_renderer_budget(self):
        source = source_worlds()
        rows, details = planned_native_visual_layers(source.layers)
        self.assertEqual(8, len(rows))
        self.assertEqual(8, details["rendered_layer_count"])
        self.assertEqual(8 * 64 * 64, details["source_cells"])
        self.assertEqual(8192, details["rendered_cells"])
        self.assertTrue(details["all_nonempty_layers_represented"])
        self.assertEqual([1024] * 8, [v["rendered_cells"] for v in rows])
        for layer, row in zip(source.layers, rows):
            self.assertEqual("balanced_spatial_v2", row["lod_strategy"])
            self.assertEqual(len(row["tiles"]), layer.width*layer.height)
            self.assertEqual(row["rendered_cells"],
                             sum(value >= 0 for value in row["tiles"]))
        self.assertEqual((rows, details),
                         planned_native_visual_layers(source.layers))

    def test_no_small_but_story_critical_layer_is_starved(self):
        counts = (65536,) + (1,)*127
        quota = allocate_visual_budgets(counts)
        self.assertEqual(8192, sum(quota))
        self.assertEqual(128, len(quota))
        self.assertEqual((1,)*127, quota[1:])
        self.assertEqual(8192 - 127, quota[0])
        with self.assertRaises(StudioError):
            allocate_visual_budgets((100,)*129)
        with self.assertRaises(StudioError):
            allocate_visual_budgets((100,)*8, 0)
        with self.assertRaises(StudioError):
            allocate_visual_budgets((2, 2, 2), 2)
        with self.assertRaises(StudioError):
            allocate_visual_budgets((1, True))

    def test_spatial_sampling_is_widespread_repeatable_and_not_terrain_forgery(self):
        original = source_worlds(width=64, height=64, count=1).layers[0]
        cells = list(original.data)
        for i in range(0, len(cells), 7):
            cells[i] = -1
        layer = replace(original, data=tuple(cells))
        sample = sample_visual_layer(layer, 16)
        self.assertEqual(16, sum(v >= 0 for v in sample))
        self.assertTrue(all(v < 0 or v == cells[i]
                            for i, v in enumerate(sample)))
        positions = [(index % layer.width, index // layer.width)
                     for index, value in enumerate(sample) if value >= 0]
        self.assertLess(min(x for x, _ in positions), 10)
        self.assertGreater(max(x for x, _ in positions), 45)
        self.assertLess(min(y for _, y in positions), 12)
        self.assertGreater(max(y for _, y in positions), 45)
        self.assertEqual(sample, sample_visual_layer(layer, 16))
        with self.assertRaises(StudioError):
            sample_visual_layer(layer, 4096)

    def test_native_godot_export_contains_every_dense_epic_layer_and_receipt(self):
        project = source_worlds()
        source = original_godot_files()
        native = add_studio_native_terrain(project, source)
        self.assertIn(_SCRIPT, native)
        self.assertIn(_DATA, native)
        self.assertEqual(3, len(native))
        self.assertNotEqual(native[_SCENE], source[_SCENE])
        self.assertIn('[node name="StudioTerrain"', native[_SCENE])
        data = json.loads(native[_DATA])
        self.assertEqual(8, data["source_layer_count"])
        self.assertEqual(8, data["rendered_layer_count"])
        self.assertEqual(8192, data["rendered_cells"])
        self.assertTrue(data["all_nonempty_layers_represented"])
        self.assertTrue(data["collision_unmodified"])
        self.assertTrue(all(v["rendered_cells"] == 1024
                            for v in data["layers"]))
        self.assertEqual(source, original_godot_files())
        with self.assertRaises(StudioError):
            add_studio_native_terrain(project, native)

    def test_small_maps_remain_lossless_and_no_earlier_scene_regression(self):
        project = source_worlds(width=8, height=8, count=2)
        native = add_studio_native_terrain(project, original_godot_files())
        result = json.loads(native[_DATA])
        self.assertEqual(128, result["source_cells"])
        self.assertEqual(128, result["rendered_cells"])
        self.assertTrue(all(row["lod_strategy"] == "exact_source"
                            for row in result["layers"]))
        self.assertTrue(all(row["tiles"] == [0]*64
                            for row in result["layers"]))

    def test_every_empty_layer_is_honestly_elided(self):
        p = source_worlds(width=8, height=8, count=3)
        sparse = replace(p.layers[1], data=(-1,)*64)
        p = replace(p, layers=(p.layers[0], sparse, p.layers[2]))
        rows, meta = planned_native_visual_layers(p.layers)
        self.assertEqual(2, len(rows))
        self.assertEqual(3, meta["source_layer_count"])
        self.assertEqual(2, meta["rendered_layer_count"])
        self.assertTrue(meta["all_nonempty_layers_represented"])


if __name__ == "__main__":
    unittest.main()
