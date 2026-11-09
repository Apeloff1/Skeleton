"""GraphML/GEXF/DOT finite topology and real canonical source custody."""
from __future__ import annotations
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.graphml_documents import extract_graphml
from skeleton.ai.webcrawler.gexf_documents import extract_gexf
from skeleton.ai.webcrawler.dot_documents import extract_dot_graph
from skeleton.ai.webcrawler.graph_topology import (
    GraphStatement,inspect_graph_statement,project_graph_topology,
)
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun

GRAPHML='''<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
<key id="secret" for="node" attr.name="SECRET_DATA" attr.type="string"/>
<graph id="world" edgedefault="directed">
  <node id="World"><data key="secret">SECRET_LOCAL_FIELD</data></node>
  <node id="Physics"/>
  <node id="Render"/>
  <node id="Unused"/>
  <edge source="World" target="Physics"/>
  <edge source="World" target="Render"/>
  <edge source="Physics" target="Render"/>
</graph></graphml>
'''
GEXF='''<?xml version="1.0" encoding="UTF-8"?>
<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">
<graph mode="static" defaultedgetype="directed">
<nodes><node id="World" label="https://outside.example.net/secret"/>
<node id="Physics"/><node id="Render"/><node id="Unused"/></nodes>
<edges><edge id="0" source="World" target="Physics"/>
<edge id="1" source="World" target="Render"/>
<edge id="2" source="Physics" target="Render"/></edges>
</graph></gexf>
'''
DOT='''digraph World {
World -> Physics;
World -> Render;
Physics -> Render;
Unused;
}
'''
UNDIRECTED='''graph World {
World -- Physics;
Physics -- Render;
}
'''

class GraphKernelTests(unittest.TestCase):
    def test_dag_measures_chain_degrees_and_isolation(self):
        graph=GraphStatement(
            ("World","Physics","Render","Unused"),
            (("World","Physics"),("World","Render"),("Physics","Render")),
            True,"Example",
        )
        row=inspect_graph_statement(graph)
        self.assertEqual(row.node_count,4)
        self.assertEqual(row.edge_count,3)
        self.assertEqual(row.weakly_connected_components,2)
        self.assertEqual(row.isolated_nodes,1)
        self.assertEqual(row.maximum_in_degree,2)
        self.assertEqual(row.maximum_out_degree,2)
        self.assertEqual(row.longest_condensed_chain,2)
        self.assertEqual(row.maximum_reverse_reach,2)
        self.assertEqual(row.strongly_connected_cycle_groups,0)
        self.assertFalse(row.network_executed)
        self.assertFalse(row.data_verified)
        self.assertEqual(inspect_graph_statement(graph),row)
        text=project_graph_topology(row,max_chars=8192)
        self.assertIn("Nodes: 4; unique arcs: 3",text.text)

    def test_cycle_and_parallel_are_finite(self):
        value=GraphStatement(
            ("a","b","c"),
            (("a","b"),("b","a"),("a","b"),("c","c")),
            True,"Cyclic source",
        )
        row=inspect_graph_statement(value)
        self.assertEqual(row.strongly_connected_cycle_groups,1)
        self.assertEqual(row.parallel_edges,1)
        self.assertEqual(row.self_loops,1)
        self.assertLessEqual(row.cyclic_nodes,row.node_count)

    def test_undirected_graph_has_symmetric_reach(self):
        row=inspect_graph_statement(GraphStatement(
            ("a","b","c"),(("a","b"),("b","c")),False,"Undirected",
        ))
        self.assertEqual(row.weakly_connected_components,1)
        self.assertEqual(row.maximum_reverse_reach,2)
        self.assertTrue(row.directed is False)

    def test_dangling_and_duplicate_nodes_rejected(self):
        with self.assertRaises(ResearchFormatError):
            inspect_graph_statement(GraphStatement(("a",),(("a","b"),),True,"Broken"))
        with self.assertRaises(ResearchFormatError):
            inspect_graph_statement(GraphStatement(("a","a"),(),True,"Duplicate"))
        with self.assertRaises(ResearchFormatError):
            inspect_graph_statement(GraphStatement(("a",)*513,(),True,"Overlarge"))

class FormatTests(unittest.TestCase):
    def test_graphml_topology_ignores_properties(self):
        row=extract_graphml(GRAPHML)
        self.assertIn("weak components: 2",row.text)
        self.assertIn("maximum",row.text.lower())
        self.assertNotIn("SECRET_LOCAL_FIELD",row.text)
        self.assertNotIn("SECRET_DATA",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_graphml_external_entities_and_duplicate_id_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_graphml('<!DOCTYPE graphml [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+GRAPHML)
        with self.assertRaises(ResearchFormatError):
            extract_graphml(GRAPHML.replace('<node id="Unused"/>','<node id="Physics"/>'))

    def test_graphml_nested_graph_and_dangling_link_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_graphml(GRAPHML.replace('<node id="Unused"/>',
                '<node id="Unused"><graph id="inner" edgedefault="directed"/></node>'))
        with self.assertRaises(ResearchFormatError):
            extract_graphml(GRAPHML.replace('target="Render"','target="Missing"'))

    def test_gexf_count_and_sensitive_label_omission(self):
        row=extract_gexf(GEXF)
        self.assertIn("Nodes: 4; unique arcs: 3",row.text)
        self.assertIn("Graph structural SHA256:",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())

    def test_gexf_xml_entities_and_invalid_edges_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_gexf('<!DOCTYPE gexf [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+GEXF)
        with self.assertRaises(ResearchFormatError):
            extract_gexf(GEXF.replace('target="Physics"','target="Unknown"'))

    def test_dot_subset_is_safe_and_inert(self):
        row=extract_dot_graph(DOT)
        self.assertIn("Nodes: 4",row.text)
        self.assertIn("weak components: 2",row.text)
        self.assertEqual(row.links,())
        row=extract_dot_graph(UNDIRECTED)
        self.assertIn("directed: False",row.text)

    def test_dot_source_embedded_html_action_denied(self):
        for bad in (
            'digraph World {\na [URL="https://outside.example.net"];\n}\n',
            'digraph World {\na -> b [label="execute"];\n}\n',
            'digraph World {\nsubgraph Q { a -> b; }\n}\n',
            'digraph World {\n// a -> secret;\na -> b;\n}\n',
        ):
            with self.subTest(value=bad),self.assertRaises(ResearchFormatError):
                extract_dot_graph(bad)

    def test_dot_missing_close_and_duplicate_identity(self):
        with self.assertRaises(ResearchFormatError):
            extract_dot_graph(DOT[:-2])

class Transport:
    timeout_seconds=4
    transport_mode="scripted_structural_graph"
    def __init__(self,mime,text):
        self.mime,self.body,self.calls=mime,text.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/graph":
            raise AssertionError("external graph attempted dynamic URL traversal")
        return FetchResponse(url,200,{"content-type":self.mime},
                             self.body,time.time())

class CanonicalGraphSourceTests(unittest.TestCase):
    def test_graph_formats_enter_original_worker_as_unreviewed(self):
        for mime,raw in (
            ("application/graphml+xml",GRAPHML),
            ("application/gexf+xml",GEXF),
            ("text/x-dot",DOT),
        ):
            with self.subTest(mime=mime):
                now=time.time()
                fetcher=Transport(mime,raw)
                run=CrawlRun.create(
                    CrawlRequest(
                        seed_urls=("https://example.com/graph",),
                        allowed_hosts=("example.com",),max_depth=1,
                        max_requests=4,max_documents=2,
                        max_response_bytes=65536,max_total_bytes=131072,
                    ),
                    scope={"tenant_id":"t","owner_id":"o"},
                    consent={"consent_id":"graph-source-rights",
                             "capture_acknowledged":True,
                             "source_rights_acknowledged":True,
                             "expires_at":now+3600},
                    now=now,fetcher=fetcher,
                )
                for offset in (1,3):
                    with patch("skeleton.ai.webcrawler.operations.time.time",
                               return_value=now+offset):
                        run.run_slice(
                            max_steps=1,max_seconds=1,authorize=lambda:None,
                            cancelled=lambda:False,
                            on_checkpoint=lambda snapshot,event:None,
                        )
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(state["frontier"],[])
                record=run.sources()[0]
                self.assertIn("Graph structural SHA256:",record["text"])
                self.assertEqual(record["review_state"],"unreviewed")
                self.assertFalse(record["provenance"]["training_permission"])
                self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

    def test_mime_scope_still_exact(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("application/graphml+xml","application/gexf+xml","text/x-dot"):
            self.assertIn(mime,allowed)
        self.assertNotIn("application/x-msdownload",allowed)

if __name__=="__main__":
    unittest.main()
