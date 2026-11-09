"""Inert Godot, Unity, USDA and LDraw scene/asset intelligence."""
from __future__ import annotations
import unittest
from skeleton.ai.webcrawler.godot_scene import extract_godot_scene
from skeleton.ai.webcrawler.unity_scene import extract_unity_scene
from skeleton.ai.webcrawler.usda_scene import extract_usda
from skeleton.ai.webcrawler.ldraw_scene import extract_ldraw
from skeleton.ai.webcrawler.research_projection import ResearchFormatError

GODOT=(
    '[gd_scene load_steps=3 format=3]\n'
    '[ext_resource type="Script" path="res://scripts/secret.gd" id="1"]\n'
    '[sub_resource type="BoxMesh" id="2"]\n'
    '[node name="FlightWorld" type="Node3D"]\n'
    '[node name="FlightCamera" type="Camera3D" parent="."]\n'
    'script = ExtResource("1")\n'
)
UNITY=(
    '%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n'
    '--- !u!1 &1001\nGameObject:\n  m_Name: FlightWorld\n'
    '--- !u!4 &1002\nTransform:\n  m_Name: FlightTransform\n'
    '--- !u!20 &1003\nCamera:\n  m_Name: FlightCamera\n'
    '  m_Script: https://outside.example.net/secret\n'
)
USDA=(
    '#usda 1.0\n'
    'def Xform "FlightWorld" {\n'
    '  def Mesh "Wing" {\n'
    '    rel references = @https://outside.example.net/secret.usd@\n'
    '  }\n'
    '  def Camera "FlightCamera" {}\n'
    '}\n'
)
LDRAW=(
    '0 Original aircraft wing demonstration\n'
    '1 16 0 0 0 1 0 0 0 1 0 0 0 1 outside.dat\n'
    '2 16 0 0 0 10 0 0\n'
    '3 16 0 0 0 10 0 0 0 10 0\n'
    '4 16 0 0 0 10 0 0 10 10 0 0 10 0\n'
)


class GodotSceneTests(unittest.TestCase):
    def test_scene_nodes_resources_without_paths(self):
        row=extract_godot_scene(GODOT)
        self.assertIn("Node3D=1",row.text)
        self.assertIn("Camera3D=1",row.text)
        self.assertIn("Script=1",row.text)
        self.assertIn("BoxMesh=1",row.text)
        self.assertNotIn("secret.gd",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_old_scene_format_not_admitted(self):
        with self.assertRaises(ResearchFormatError):
            extract_godot_scene(GODOT.replace("format=3","format=2"))

    def test_resource_without_type_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_godot_scene(GODOT.replace('type="BoxMesh" ',''))

    def test_node_cap_denied(self):
        raw='[gd_scene format=3]\n'+'[node name="N" type="Node3D"]\n'*2049
        with self.assertRaises(ResearchFormatError):
            extract_godot_scene(raw)


class UnitySceneTests(unittest.TestCase):
    def test_unity_yaml_class_count_never_executed(self):
        row=extract_unity_scene(UNITY)
        self.assertIn("Serialized object records: 3",row.text)
        self.assertIn("GameObject=1",row.text)
        self.assertIn("Camera=1",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())

    def test_duplicate_yaml_file_identity_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_unity_scene(UNITY.replace("&1002","&1001"))

    def test_unity_without_unity_magic_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_unity_scene(UNITY.replace("%YAML 1.1","invalid"))

    def test_malformed_doc_header_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_unity_scene(UNITY.replace("--- !u!20 &1003","--- malformed"))


class USDASceneTests(unittest.TestCase):
    def test_source_prim_topology_without_external_reference(self):
        row=extract_usda(USDA)
        self.assertIn("Declared prims: 3",row.text)
        self.assertIn("Xform=1",row.text)
        self.assertIn("Mesh=1",row.text)
        self.assertIn("Camera=1",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())

    def test_unsupported_usd_magic_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_usda(USDA.replace("#usda 1.0","#usda 2.0"))

    def test_missing_prims_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_usda("#usda 1.0\n# external references only")


class LDrawTests(unittest.TestCase):
    def test_inert_part_refs_and_geometry_classes(self):
        row=extract_ldraw(LDRAW)
        self.assertIn("Part references (not loaded): 1",row.text)
        self.assertIn("triangle primitives: 1",row.text)
        self.assertIn("Quadrilateral primitives: 1",row.text)
        self.assertNotIn("outside.dat",row.text)
        self.assertEqual(row.links,())

    def test_bad_external_part_reference_still_never_loaded(self):
        row=extract_ldraw(LDRAW.replace("outside.dat","../../private.key"))
        self.assertEqual(row.links,())
        self.assertNotIn("private.key",row.text)

    def test_missing_primitive_components_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ldraw("0 description\n2 16 0 0 0 1 1")

    def test_unbounded_primitive_coordinates_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_ldraw("3 16 0 0 0 1e100 0 0 0 1 0")


if __name__=="__main__":
    unittest.main()
