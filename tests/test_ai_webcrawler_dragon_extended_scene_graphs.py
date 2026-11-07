"""Unity Transform and USD prim topology, malformed links, source replay."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.unity_hierarchy import inspect_unity_hierarchy
from skeleton.ai.webcrawler.usda_hierarchy import inspect_usda_hierarchy
from skeleton.ai.webcrawler.unity_scene import extract_unity_scene
from skeleton.ai.webcrawler.usda_scene import extract_usda
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest

UNITY='''%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100
GameObject:
  m_Name: WorldRoot
--- !u!4 &200
Transform:
  m_Father: {fileID: 0}
--- !u!4 &201
Transform:
  m_Father: {fileID: 200}
--- !u!224 &202
RectTransform:
  m_Father: {fileID: 200}
--- !u!114 &300
MonoBehaviour:
  m_Script: {fileID: 12345, guid: SECRET_GUID}
  m_Name: https://outside.example.net/private
'''
USD='''#usda 1.0
def Xform "FlightWorld" {
    def Mesh "Wing" {
        def Xform "Thruster" {}
        rel references = @https://outside.example.net/private.usd@
    }
    def Camera "FlightCamera" {}
}
'''

class UnityTests(unittest.TestCase):
    def test_local_transform_tree_without_mono_behaviour(self):
        row=inspect_unity_hierarchy(UNITY)
        self.assertIsNotNone(row)
        self.assertEqual(row.transform_count,3)
        self.assertEqual(row.unresolved_parent_count,0)
        self.assertEqual(row.topology.node_count,3)
        self.assertEqual(row.topology.root_count,1)
        self.assertEqual(row.topology.edge_count,2)
        self.assertEqual(row.topology.maximum_depth,1)
        self.assertEqual(row.topology.maximum_children,2)
        self.assertFalse(row.prefab_loaded)
        text=extract_unity_scene(UNITY).text
        self.assertIn("Hierarchy depth: 1",text)
        self.assertIn("RectTransform",text)
        self.assertNotIn("SECRET_GUID",text)
        self.assertNotIn("outside.example.net",text)
    def test_unknown_parent_is_counted_not_resolved(self):
        broken=UNITY.replace("m_Father: {fileID: 200}",
                             "m_Father: {fileID: 999}",1)
        row=inspect_unity_hierarchy(broken)
        self.assertEqual(row.unresolved_parent_count,1)
        self.assertEqual(row.topology.edge_count,1)
    def test_cyclic_transform_rejected(self):
        broken=UNITY.replace("m_Father: {fileID: 0}","m_Father: {fileID: 201}")
        with self.assertRaises(ResearchFormatError):
            inspect_unity_hierarchy(broken)
    def test_duplicate_identity_and_parent_rejected(self):
        with self.assertRaises(ResearchFormatError):
            inspect_unity_hierarchy(UNITY.replace("!u!224 &202","!u!224 &200"))
        with self.assertRaises(ResearchFormatError):
            inspect_unity_hierarchy(UNITY.replace(
                "m_Father: {fileID: 200}",
                "m_Father: {fileID: 200}\n  m_Father: {fileID: 0}",1,
            ))
    def test_no_transforms_is_not_fabricated(self):
        self.assertIsNone(inspect_unity_hierarchy(
            "%YAML 1.1\n--- !u!1 &100\nGameObject:\n",
        ))

class USDTests(unittest.TestCase):
    def test_nested_prim_graph_and_inert_references(self):
        row=inspect_usda_hierarchy(USD)
        self.assertEqual(row.node_count,4)
        self.assertEqual(row.edge_count,3)
        self.assertEqual(row.maximum_depth,2)
        self.assertEqual(row.root_count,1)
        self.assertEqual(row.leaf_count,2)
        self.assertFalse(row.renderer_executed)
        summary=extract_usda(USD).text
        self.assertIn("Hierarchy depth: 2",summary)
        self.assertIn("Scene topology SHA256:",summary)
        self.assertNotIn("outside.example.net",summary)
    def test_magic_and_unknown_prim_format_rejected(self):
        with self.assertRaises(ResearchFormatError):
            inspect_usda_hierarchy(USD.replace("#usda 1.0","#usda 2.0"))
    def test_duplicate_scene_paths_rejected(self):
        with self.assertRaises(ResearchFormatError):
            inspect_usda_hierarchy(USD.replace(
                'def Camera "FlightCamera" {}','def Mesh "Wing" {}',
            ))
    def test_unclosed_scope_and_stray_close_rejected(self):
        with self.assertRaises(ResearchFormatError):
            inspect_usda_hierarchy(USD.rsplit("}",1)[0])
        with self.assertRaises(ResearchFormatError):
            inspect_usda_hierarchy(USD+"}\n")
    def test_deep_prim_tree_rejected(self):
        value="#usda 1.0\n"+('def Xform "Level" {\n'*34)+("}\n"*34)
        with self.assertRaises(ResearchFormatError):
            inspect_usda_hierarchy(value)

class Transport:
    timeout_seconds=4
    transport_mode="scripted_scene_hierarchy"
    def __init__(self,mime,body):
        self.mime,self.body,self.calls=mime,body.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/scene":
            raise AssertionError("scene attempted unauthorized resource request")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())

class CanonicalTests(unittest.TestCase):
    def test_unity_usd_scene_receipts_and_exact_replay(self):
        for mime,source in (("application/x-unity-scene",UNITY),
                            ("model/vnd.usda",USD)):
            with self.subTest(mime=mime):
                now=time.time()
                fetcher=Transport(mime,source)
                run=CrawlRun.create(
                    CrawlRequest(seed_urls=("https://example.com/scene",),
                        allowed_hosts=("example.com",),max_requests=4,
                        max_documents=2,max_depth=1,max_response_bytes=65536,
                        max_total_bytes=131072),
                    scope={"tenant_id":"t","owner_id":"o"},
                    consent={"consent_id":"scene-rights","capture_acknowledged":True,
                             "source_rights_acknowledged":True,"expires_at":now+3600},
                    now=now,fetcher=fetcher)
                for offset in (1,3):
                    with patch("skeleton.ai.webcrawler.operations.time.time",
                               return_value=now+offset):
                        run.run_slice(max_steps=1,max_seconds=1,
                            authorize=lambda:None,cancelled=lambda:False,
                            on_checkpoint=lambda snap,event:None)
                state=run.snapshot()
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                self.assertIn("Scene topology SHA256:",run.sources()[0]["text"])
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

if __name__=="__main__":
    unittest.main()
