"""Deep source-side SBOM dependency graph, license and VEX claim boundary."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.sbom_graph import (
    SBOMComponent, SBOMEdge, make_sbom_graph,
)
from skeleton.ai.webcrawler.cyclonedx_documents import extract_cyclonedx
from skeleton.ai.webcrawler.spdx_documents import extract_spdx
from skeleton.ai.webcrawler.vex_documents import extract_openvex
from skeleton.ai.webcrawler.research_projection import ResearchFormatError

CYCLO = {
    "bomFormat":"CycloneDX","specVersion":"1.6","serialNumber":"urn:uuid:fake-source-identity",
    "metadata":{"component":{"name":"SECRET_METADATA_SHOULD_NOT_LEAK"},
                "tools":[{"url":"https://outside.example.net/hidden"}]},
    "components":[
        {"bom-ref":"component-root","name":"Original flight engine",
         "version":"1.5.2","type":"application",
         "purl":"pkg:pypi/flight-core@1.5.2",
         "licenses":[{"license":{"id":"MIT"}}],
         "hashes":[{"alg":"SHA-256","content":"SECRET_HASH_STRING"}]},
        {"bom-ref":"component-solver","name":"Aerodynamic solver",
         "version":"2.0","purl":"pkg:npm/solver@2.0",
         "licenses":[{"expression":"MIT OR Apache-2.0"}]},
        {"bom-ref":"component-optional","name":"Original scenes",
         "version":"0.9","licenses":[]},
    ],
    "dependencies":[
        {"ref":"component-root","dependsOn":["component-solver","component-optional"]},
        {"ref":"component-solver","dependsOn":["component-optional"]},
    ],
    "vulnerabilities":[{"description":"SECRET_VULNERABILITY_BODY"}],
    "formulation":[{"url":"https://outside.example.net/script"}],
}
SPDX = {
    "spdxVersion":"SPDX-2.3",
    "dataLicense":"CC0-1.0",
    "SPDXID":"SPDXRef-DOCUMENT",
    "documentNamespace":"https://outside.example.net/SECRET_NAMESPACE",
    "packages":[
        {"SPDXID":"SPDXRef-Flight","name":"Original flight engine",
         "versionInfo":"1.5.2","licenseDeclared":"MIT",
         "externalRefs":[{"referenceType":"purl",
                          "referenceLocator":"pkg:pypi/flight@1.5.2"}],
         "checksums":[{"algorithm":"SHA256","checksumValue":"SECRET_CHECKSUM"}],
         "downloadLocation":"https://outside.example.net/SECRET_DOWNLOAD"},
        {"SPDXID":"SPDXRef-Solver","name":"Wing solver","versionInfo":"2.0",
         "licenseDeclared":"NOASSERTION"},
    ],
    "relationships":[
        {"spdxElementId":"SPDXRef-Flight",
         "relationshipType":"DEPENDS_ON","relatedSpdxElement":"SPDXRef-Solver"},
        {"spdxElementId":"SPDXRef-DOCUMENT",
         "relationshipType":"DESCRIBES","relatedSpdxElement":"SPDXRef-Flight"},
    ],
    "files":[{"fileName":"SECRET_FILE_PATH"}],
}
VEX = {
    "@context":"https://openvex.dev/ns/v0.2.0",
    "@id":"https://outside.example.net/SECRET_ID",
    "author":"Source publisher",
    "statements":[
        {"vulnerability":{"name":"CVE-2026-12345",
                          "description":"SECRET_VULNERABILITY_DETAIL"},
         "products":["pkg:pypi/flight@1.5.2?api_key=SECRET_PRODUCT"],
         "status":"not_affected","status_justification":"vulnerable_code_not_present"},
        {"vulnerability":{"name":"CVE-2026-54321"},
         "products":["pkg:npm/solver@2.0"],"status":"under_investigation"},
    ],
}

class GraphContractTests(unittest.TestCase):
    def test_topology_and_license_denials_are_measured_not_certified(self):
        graph=make_sbom_graph(
            [SBOMComponent("a","Flight","1",declared_license="MIT"),
             SBOMComponent("b","Wing","2"),
             SBOMComponent("c","Scene","3")],
            [SBOMEdge("a","b"),SBOMEdge("b","c")],
        )
        self.assertEqual(graph.roots,("a",))
        self.assertEqual(graph.cyclic_nodes,0)
        self.assertEqual(graph.license_unknown,2)
        self.assertEqual(graph.highest_outdegree,1)
        self.assertFalse(graph.statements_verified)
        self.assertFalse(graph.training_permission)

    def test_dependency_cycle_is_flagged_not_claimed_acyclic(self):
        graph=make_sbom_graph(
            [SBOMComponent("a","A",""),SBOMComponent("b","B","")],
            [SBOMEdge("a","b"),SBOMEdge("b","a")],
        )
        self.assertEqual(graph.cyclic_nodes,2)
        self.assertEqual(graph.roots,())

    def test_unresolved_dependency_is_explicit_not_silently_authorized(self):
        graph=make_sbom_graph(
            [SBOMComponent("a","A","")],[SBOMEdge("a","missing")],
        )
        self.assertEqual(graph.unresolved_references,("missing",))
        self.assertEqual(len(graph.dependencies),0)

    def test_duplicated_nodes_and_edges_denied(self):
        with self.assertRaises(ResearchFormatError):
            make_sbom_graph(
                [SBOMComponent("a","A",""),SBOMComponent("a","A","")],[],
            )
        with self.assertRaises(ResearchFormatError):
            make_sbom_graph(
                [SBOMComponent("a","A",""),SBOMComponent("b","B","")],
                [SBOMEdge("a","b"),SBOMEdge("a","b")],
            )

    def test_self_dependent_components_denied(self):
        with self.assertRaises(ResearchFormatError):
            make_sbom_graph([SBOMComponent("a","A","")],[SBOMEdge("a","a")])

    def test_bounded_graph_capacity(self):
        with self.assertRaises(ResearchFormatError):
            make_sbom_graph([SBOMComponent(f"c{i}",f"Component{i}","1")
                             for i in range(513)],[])


class CycloneDXTests(unittest.TestCase):
    def test_real_component_topology_with_provenance_barrier(self):
        row=extract_cyclonedx(json.dumps(CYCLO))
        self.assertIn("Original flight engine",row.text)
        self.assertIn("Aerodynamic solver",row.text)
        self.assertIn("Components: 3; dependencies: 3",row.text)
        self.assertIn("claim",row.text.lower())
        self.assertIn("claimed_license: MIT",row.text)
        self.assertIn("claimed_license: NOASSERTION",row.text)
        for private in ("SECRET_HASH_STRING","SECRET_METADATA_SHOULD_NOT_LEAK",
                        "SECRET_VULNERABILITY_BODY","outside.example.net"):
            self.assertNotIn(private,row.text)
        self.assertFalse(row.body_executed)
        self.assertFalse(row.reference_trusted)
        self.assertEqual(row.links,())

    def test_invalid_spec_version_denied(self):
        obj={**CYCLO,"specVersion":"5.0"}
        with self.assertRaises(ResearchFormatError):
            extract_cyclonedx(json.dumps(obj))

    def test_duplicate_package_identity_denied(self):
        obj={**CYCLO,"components":[CYCLO["components"][0]]*2}
        with self.assertRaises(ResearchFormatError):
            extract_cyclonedx(json.dumps(obj))

    def test_duplicate_json_keys_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_cyclonedx('{"bomFormat":"CycloneDX","specVersion":"1.6",'
                              '"components":[],"components":[]}')

    def test_oversized_dependency_fanout_denied(self):
        obj={**CYCLO,"dependencies":[{"ref":"component-root",
                                       "dependsOn":["component-solver"]*65}]}
        with self.assertRaises(ResearchFormatError):
            extract_cyclonedx(json.dumps(obj))


class SPDXTests(unittest.TestCase):
    def test_dependency_path_and_declared_license(self):
        row=extract_spdx(json.dumps(SPDX))
        self.assertIn("Original flight engine",row.text)
        self.assertIn("Components: 2; dependencies: 1",row.text)
        self.assertIn("claimed_license: MIT",row.text)
        self.assertIn("claimed_license: NOASSERTION",row.text)
        self.assertNotIn("SECRET_CHECKSUM",row.text)
        self.assertNotIn("SECRET_DOWNLOAD",row.text)
        self.assertNotIn("SECRET_NAMESPACE",row.text)
        self.assertFalse(row.reference_trusted)

    def test_dependency_of_direction_normalized(self):
        obj={**SPDX,"relationships":[{"spdxElementId":"SPDXRef-Solver",
                "relatedSpdxElement":"SPDXRef-Flight",
                "relationshipType":"DEPENDENCY_OF"}]}
        row=extract_spdx(json.dumps(obj))
        self.assertIn("dependencies: 1",row.text)

    def test_unknown_spdx_version_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_spdx(json.dumps({**SPDX,"spdxVersion":"SPDX-3.0"}))

    def test_checksum_limit_fail_closed(self):
        obj=json.loads(json.dumps(SPDX))
        obj["packages"][0]["checksums"]=[{"algorithm":"SHA256"}]*17
        with self.assertRaises(ResearchFormatError):
            extract_spdx(json.dumps(obj))


class OpenVEXTests(unittest.TestCase):
    def test_unverified_security_assertions_not_training_permissions(self):
        row=extract_openvex(json.dumps(VEX))
        self.assertIn("CVE-2026-12345",row.text)
        self.assertIn("supplier_claim: not_affected",row.text)
        self.assertIn("independently_verified: False",row.text)
        self.assertIn("under_investigation",row.text)
        for private in ("SECRET_PRODUCT","SECRET_VULNERABILITY_DETAIL",
                        "SECRET_ID","outside.example.net"):
            self.assertNotIn(private,row.text)
        self.assertEqual(row.links,())

    def test_invalid_status_cannot_become_verified(self):
        obj=json.loads(json.dumps(VEX))
        obj["statements"][0]["status"]="certified_secure"
        with self.assertRaises(ResearchFormatError):
            extract_openvex(json.dumps(obj))

    def test_missing_products_denied(self):
        obj=json.loads(json.dumps(VEX))
        obj["statements"][0]["products"]=[]
        with self.assertRaises(ResearchFormatError):
            extract_openvex(json.dumps(obj))


class SourceTransport:
    timeout_seconds=4
    transport_mode="scripted_sbom_provenance"
    def __init__(self,mime,document):
        self.mime,self.body,self.calls=mime,json.dumps(document).encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/software":
            raise AssertionError("SBOM/VEX source requested a package or supplier URL")
        if len(self.body)>max_bytes:
            raise AssertionError("scripted response exceeds pre-reserved byte bound")
        return FetchResponse(url,200,{"content-type":self.mime},
                             self.body,time.time())


class CanonicalSoftwareSourceTests(unittest.TestCase):
    def capture(self,mime,document):
        at=time.time()
        fetcher=SourceTransport(mime,document)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/software",),
                allowed_hosts=("example.com",),max_depth=1,
                max_requests=4,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"software-source-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,"expires_at":at+3600},
            now=at,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=at+offset):
                run.run_slice(
                    max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None,
                )
        return run,fetcher

    def test_three_inventory_formats_captured_canonically(self):
        for mime,document,marker in (
            ("application/vnd.cyclonedx+json",CYCLO,"Aerodynamic solver"),
            ("application/spdx+json",SPDX,"Wing solver"),
            ("application/vnd.openvex+json",VEX,"CVE-2026-12345"),
        ):
            with self.subTest(mime=mime):
                run,fetcher=self.capture(mime,document)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                self.assertEqual(len(fetcher.calls),2)
                source=run.sources()[0]
                self.assertIn(marker,source["text"])
                self.assertEqual(source["review_state"],"unreviewed")
                self.assertFalse(source["provenance"]["training_permission"])
                self.assertFalse(source["provenance"]["raw_bytes_retained"])
                self.assertEqual(
                    CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),
                    state,
                )

    def test_malformed_suppliers_charged_but_not_retained(self):
        run,fetcher=self.capture(
            "application/vnd.cyclonedx+json",
            {"bomFormat":"CycloneDX","specVersion":"1.6","components":[]},
        )
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)

    def test_source_url_beyond_policy_never_dispatched(self):
        run,fetcher=self.capture("application/vnd.openvex+json",VEX)
        self.assertEqual(len(fetcher.calls),2)
        self.assertFalse(run.snapshot()["frontier"])

    def test_canonical_media_allowlist_closed(self):
        policy=CrawlPolicy(allowed_hosts=frozenset({"example.com"}))
        for mime in ("application/vnd.cyclonedx+json",
                     "application/spdx+json","application/vnd.openvex+json"):
            self.assertIn(mime,policy.allowed_content_types)


if __name__=="__main__":
    unittest.main()
