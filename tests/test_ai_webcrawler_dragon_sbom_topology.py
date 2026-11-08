"""Finite dependency SCC, transitive reach, reverse blast radius and custody."""
from __future__ import annotations
import json
import unittest

from skeleton.ai.webcrawler.sbom_graph import (
    SBOMComponent,SBOMEdge,make_sbom_graph,project_sbom,
)
from skeleton.ai.webcrawler.sbom_topology import inspect_sbom_topology
from skeleton.ai.webcrawler.cyclonedx_documents import extract_cyclonedx
from skeleton.ai.webcrawler.npm_lock_documents import extract_npm_lock
from skeleton.ai.webcrawler.research_projection import ResearchFormatError


def graph(names,links):
    return make_sbom_graph(
        [SBOMComponent(x,x,"1.0",ecosystem="npm") for x in names],
        [SBOMEdge(a,b) for a,b in links],
    )


class TopologyTests(unittest.TestCase):
    def test_long_chain_exact_transitive_depth_and_reverse_impact(self):
        g=graph(("a","b","c","d"),(("a","b"),("b","c"),("c","d")))
        t=inspect_sbom_topology(g)
        self.assertEqual(t.component_count,4)
        self.assertEqual(t.dependency_edges,3)
        self.assertEqual(t.truly_cyclic_nodes,0)
        self.assertEqual(t.cyclic_strong_components,0)
        self.assertEqual(t.maximum_transitive_dependencies,3)
        self.assertEqual(t.maximum_reverse_impact,3)
        self.assertEqual(t.longest_condensed_chain,3)
        self.assertEqual(t.root_reachable_nodes,4)
        self.assertEqual(t.hotspots[0].component_id,"d")
        self.assertEqual(t.hotspots[0].upstream_dependents,3)
        self.assertFalse(t.independently_verified)
        self.assertFalse(t.network_executed)
        self.assertEqual(inspect_sbom_topology(g),t)

    def test_cycle_nodes_not_confused_with_downstream_blocked_nodes(self):
        g=graph(("a","b","c","d"),(("a","b"),("b","a"),("b","c"),("c","d")))
        t=inspect_sbom_topology(g)
        self.assertEqual(t.truly_cyclic_nodes,2)
        self.assertEqual(t.cyclic_strong_components,1)
        self.assertEqual(t.largest_strong_component,2)
        self.assertEqual(t.longest_condensed_chain,2)
        self.assertEqual(t.maximum_transitive_dependencies,3)
        # Kahn's old cyclic_nodes includes downstream c/d; SCC does not.
        self.assertEqual(g.cyclic_nodes,4)
        self.assertEqual(t.root_reachable_nodes,0)

    def test_diamond_topology_no_double_counted_reachability(self):
        g=graph(("root","left","right","leaf"),(
            ("root","left"),("root","right"),
            ("left","leaf"),("right","leaf"),
        ))
        t=inspect_sbom_topology(g)
        self.assertEqual(t.maximum_transitive_dependencies,3)
        self.assertEqual(t.maximum_reverse_impact,3)
        self.assertEqual(t.hotspots[0].component_id,"leaf")
        self.assertEqual(t.longest_condensed_chain,2)

    def test_disconnected_components_and_deterministic_order(self):
        a=graph(("x","a","b"),(("a","b"),))
        b=graph(("b","x","a"),(("a","b"),))
        self.assertEqual(a.graph_digest,b.graph_digest)
        self.assertEqual(inspect_sbom_topology(a).topology_digest,
                         inspect_sbom_topology(b).topology_digest)
        self.assertEqual(inspect_sbom_topology(a).root_reachable_nodes,3)

    def test_projection_contains_structural_impact_not_external_ids(self):
        g=graph(("one","two","three"),(("one","two"),("two","three")))
        output=project_sbom(g,kind="synthetic safe source",max_chars=8192)
        self.assertIn("Maximum reverse dependency impact: 2",output.text)
        self.assertIn("True cycle member nodes: 0",output.text)
        self.assertIn("Dependency topology fingerprint SHA256:",output.text)
        self.assertFalse(output.reference_trusted)

    def test_capacity_and_noncanonical_topology_refused(self):
        g=graph(("a","b"),(("a","b"),))
        with self.assertRaises(ResearchFormatError):
            inspect_sbom_topology(g,max_hotspots=0)
        with self.assertRaises(ResearchFormatError):
            inspect_sbom_topology(None)

    def test_cyclonedx_parser_now_emits_topology_on_real_source(self):
        source={"bomFormat":"CycloneDX","specVersion":"1.6",
                "components":[
                    {"bom-ref":"a","name":"Game"},
                    {"bom-ref":"b","name":"Physics"},
                    {"bom-ref":"c","name":"World"},
                ],
                "dependencies":[
                    {"ref":"a","dependsOn":["b"]},
                    {"ref":"b","dependsOn":["c"]},
                ]}
        row=extract_cyclonedx(json.dumps(source))
        self.assertIn("Maximum transitive dependencies: 2",row.text)
        self.assertIn("Maximum reverse dependency impact: 2",row.text)
        self.assertEqual(row.links,())

    def test_npm_lock_custody_projection_includes_topology(self):
        source={"lockfileVersion":3,"packages":{
            "":{"name":"root","dependencies":{"wing":"1"}},
            "node_modules/wing":{"name":"wing","version":"1"},
        }}
        out=extract_npm_lock(json.dumps(source))
        self.assertIn("Maximum transitive dependencies: 1",out.text)
        self.assertNotIn("http",out.text)


if __name__=="__main__":
    unittest.main()
