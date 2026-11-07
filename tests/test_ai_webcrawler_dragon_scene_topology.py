"""Bounded game-scene parent/child DAG and canonical Godot source capture."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.scene_topology import (
    SceneNode,SceneEdge,analyze_scene_topology,summarize_scene_topology,
)
from skeleton.ai.webcrawler.godot_hierarchy import inspect_godot_hierarchy
from skeleton.ai.webcrawler.godot_scene import extract_godot_scene
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest

GODOT='''[gd_scene load_steps=4 format=3]
[ext_resource type="Script" path="res://PRIVATE_SCRIPT.gd" id="1"]
[sub_resource type="BoxMesh" id="2"]
[node name="FlightWorld" type="Node3D"]
[node name="Wing" type="MeshInstance3D" parent="."]
mesh = SubResource("2")
[node name="Thruster" type="Node3D" parent="Wing"]
script = ExtResource("1")
[node name="Particle" type="GPUParticles3D" parent="Wing/Thruster"]
'''

class SceneGraphContractTests(unittest.TestCase):
    def test_graph_depth_edges_fanout_and_digest(self):
        row=analyze_scene_topology("Godot",[
            SceneNode("root","Node3D","Game"),
            SceneNode("wing","MeshInstance3D","Wing"),
            SceneNode("light","OmniLight3D","Light"),
            SceneNode("fin","Node3D","Fin"),
        ],[
            SceneEdge("root","wing"),SceneEdge("root","light"),
            SceneEdge("wing","fin"),
        ])
        self.assertEqual(row.node_count,4)
        self.assertEqual(row.edge_count,3)
        self.assertEqual(row.root_count,1)
        self.assertEqual(row.leaf_count,2)
        self.assertEqual(row.maximum_depth,2)
        self.assertEqual(row.maximum_children,2)
        self.assertEqual(len(row.canonical_digest),64)
        self.assertFalse(row.renderer_executed)
        self.assertFalse(row.imports_loaded)
        self.assertFalse(row.game_build_authorized)
        self.assertIn("Hierarchy depth: 2",summarize_scene_topology(row)[2])

    def test_cyclic_graph_fails_closed(self):
        nodes=[SceneNode(name,"Node3D",name) for name in ("a","b","c")]
        with self.assertRaises(ResearchFormatError):
            analyze_scene_topology("Godot",nodes,[
                SceneEdge("a","b"),SceneEdge("b","a"),
            ])

    def test_multiple_parent_graph_fails_closed(self):
        nodes=[SceneNode(name,"Node3D",name) for name in ("a","b","c")]
        with self.assertRaises(ResearchFormatError):
            analyze_scene_topology("Godot",nodes,[
                SceneEdge("a","c"),SceneEdge("b","c"),
            ])

    def test_missing_parent_or_duplicate_edges_fail(self):
        nodes=[SceneNode("a","Node3D","A"),SceneNode("b","Node3D","B")]
        with self.assertRaises(ResearchFormatError):
            analyze_scene_topology("Godot",nodes,[SceneEdge("ghost","b")])
        with self.assertRaises(ResearchFormatError):
            analyze_scene_topology("Godot",nodes,[
                SceneEdge("a","b"),SceneEdge("a","b"),
            ])

    def test_source_order_does_not_change_canonical_digest(self):
        nodes=[SceneNode("a","Node3D","Root"),SceneNode("b","Camera3D","Camera")]
        edge=[SceneEdge("a","b")]
        first=analyze_scene_topology("Godot",nodes,edge)
        second=analyze_scene_topology("Godot",list(reversed(nodes)),edge)
        self.assertEqual(first.canonical_digest,second.canonical_digest)

    def test_graph_capacity_and_identity(self):
        node=SceneNode("root","Node3D","Scene")
        with self.assertRaises(ResearchFormatError):
            analyze_scene_topology("Godot",[node],[],max_nodes=0)
        with self.assertRaises(ResearchFormatError):
            analyze_scene_topology("Godot",[node,node],[])

class GodotHierarchyTests(unittest.TestCase):
    def test_multilevel_godot_parent_paths(self):
        topology=inspect_godot_hierarchy(GODOT)
        self.assertEqual(topology.node_count,4)
        self.assertEqual(topology.edge_count,3)
        self.assertEqual(topology.root_count,1)
        self.assertEqual(topology.maximum_depth,3)
        self.assertEqual(topology.leaf_count,1)
        projected=extract_godot_scene(GODOT)
        self.assertIn("Hierarchy depth: 3",projected.text)
        self.assertIn("Scene topology SHA256:",projected.text)
        self.assertNotIn("PRIVATE_SCRIPT.gd",projected.text)
        self.assertEqual(projected.links,())
        self.assertFalse(projected.body_executed)

    def test_unknown_parent_disallowed(self):
        raw=GODOT.replace('parent="Wing/Thruster"','parent="Missing"')
        with self.assertRaises(ResearchFormatError):
            inspect_godot_hierarchy(raw)

    def test_parent_escape_disallowed(self):
        with self.assertRaises(ResearchFormatError):
            inspect_godot_hierarchy(
                GODOT.replace('parent="Wing/Thruster"','parent="../secret"')
            )

    def test_duplicate_full_scene_identity_disallowed(self):
        broken=GODOT+('[node name="Wing" type="Node3D" parent="."]\n')
        with self.assertRaises(ResearchFormatError):
            inspect_godot_hierarchy(broken)

    def test_second_root_disallowed(self):
        with self.assertRaises(ResearchFormatError):
            inspect_godot_hierarchy(
                GODOT+'[node name="OtherRoot" type="Node3D"]\n',
            )

class ScriptedGodotTransport:
    timeout_seconds=4
    transport_mode="scripted_godot_hierarchy"
    def __init__(self):
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/game-scene":
            raise AssertionError("Godot resource path attempted outbound fetch")
        return FetchResponse(url,200,{"content-type":"application/x-godot-scene"},
                             GODOT.encode(),time.time())

class CanonicalGodotSourceTests(unittest.TestCase):
    def test_scene_graph_captured_and_replayed_in_original_worker(self):
        at=time.time()
        fetcher=ScriptedGodotTransport()
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/game-scene",),
                allowed_hosts=("example.com",),max_depth=1,
                max_requests=4,max_documents=2,max_response_bytes=65536,
                max_total_bytes=131072,
            ),
            scope={"tenant_id":"t","owner_id":"o"},
            consent={"consent_id":"godot-hierarchy-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,"expires_at":at+3600},
            now=at,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                              cancelled=lambda:False,
                              on_checkpoint=lambda snap,event:None)
        state=run.snapshot()
        self.assertEqual(len(fetcher.calls),2)
        self.assertEqual(state["usage"]["documents"],1)
        self.assertEqual(state["usage"]["requests"],2)
        self.assertIn("Hierarchy depth: 3",run.sources()[0]["text"])
        self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
        self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
        self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

if __name__=="__main__":
    unittest.main()
