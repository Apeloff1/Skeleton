"""Source-only OpenAPI schema refs, graph cycles, code bounds, canonical capture."""
from __future__ import annotations
import copy
import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.openapi_graph import (
    inspect_openapi_graph,summarize_openapi_graph,
)
from skeleton.ai.webcrawler.openapi_documents import extract_openapi
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRun,CrawlRequest

DOC={
    "openapi":"3.1.0",
    "info":{"title":"Flight control contract"},
    "servers":[{"url":"https://outside.example.net/private?token=SECRET"}],
    "security":[{"BearerAuth":[]}],
    "components":{
        "schemas":{
            "Airframe":{"type":"object","properties":{
                "wing":{"$ref":"#/components/schemas/Wing"},
                "external":{"$ref":"https://outside.example.net/SECRET_SCHEMA"},
            }},
            "Wing":{"type":"object","properties":{
                "engine":{"$ref":"#/components/schemas/Engine"}
            }},
            "Engine":{"allOf":[{"$ref":"#/components/schemas/Wing"}]},
            "Envelope":{"properties":{
                "unknown":{"$ref":"#/components/schemas/Unresolved"},
            }},
        },
        "securitySchemes":{"BearerAuth":{"type":"http","scheme":"bearer"}},
    },
    "paths":{
        "/aircraft/{id}":{
            "get":{
                "operationId":"readAircraft",
                "summary":"Read aircraft specification",
                "responses":{"200":{"description":"Flight profile","content":{
                    "application/json":{"schema":{"$ref":"#/components/schemas/Airframe"}}
                }},"404":{"description":"missing"}},
                "security":[{"BearerAuth":[]}],
            },
            "post":{
                "operationId":"proposeFlight",
                "summary":"Propose flight configuration",
                "requestBody":{"content":{
                    "application/json":{"schema":{"$ref":"#/components/schemas/Airframe"}}
                }},
                "responses":{"201":{"description":"created"}},
                "security":[{"BearerAuth":[]}]
            },
        },
    },
    "x-internal-script":"SECRET_ACTION_NOT_EXECUTED",
}

class GraphContractTests(unittest.TestCase):
    def test_cycle_graph_is_structural_and_unverified(self):
        report=inspect_openapi_graph(DOC)
        self.assertEqual(report.path_count,1)
        self.assertEqual(report.operation_count,2)
        self.assertEqual(report.declared_schema_count,4)
        self.assertEqual(report.cyclic_schema_nodes,2)
        self.assertEqual(report.schema_cycles,1)
        self.assertEqual(report.unresolved_local_references,1)
        self.assertEqual(report.ignored_external_references,1)
        self.assertEqual(report.operations_with_security_requirements,2)
        self.assertEqual(report.method_counts,(("get",1),("post",1)))
        self.assertFalse(report.remote_schema_resolved)
        self.assertFalse(report.HTTP_executed)
        self.assertFalse(report.schema_validated)
        self.assertEqual(len(report.topology_digest),64)
        self.assertEqual(report,inspect_openapi_graph(copy.deepcopy(DOC)))

    def test_projection_omits_remote_url_and_examples(self):
        row=extract_openapi(json.dumps(DOC))
        self.assertIn("Flight control contract",row.title)
        self.assertIn("Schema cycles: 1",row.text)
        self.assertIn("true cyclic schemas: 2",row.text)
        self.assertIn("API operation methods: GET=1, POST=1",row.text)
        self.assertIn("GET /aircraft/{id}",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertNotIn("SECRET_ACTION",row.text)
        self.assertNotIn("SECRET_SCHEMA",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.body_executed)

    def test_acyclic_schema_chain_has_finite_depth(self):
        data=copy.deepcopy(DOC)
        data["components"]["schemas"]["Engine"]={"type":"string"}
        report=inspect_openapi_graph(data)
        self.assertEqual(report.schema_cycles,0)
        self.assertEqual(report.longest_schema_dependency_chain,2)

    def test_schema_count_limit_fail_closed(self):
        data=copy.deepcopy(DOC)
        data["components"]["schemas"]={
            f"Schema{i}":{"type":"string"} for i in range(257)
        }
        with self.assertRaises(ResearchFormatError):
            inspect_openapi_graph(data)

    def test_duplicate_json_keys_denied_by_canonical_parser(self):
        with self.assertRaises(ResearchFormatError):
            extract_openapi('{"openapi":"3.1","paths":{},"paths":{}}')

    def test_recursive_schema_depth_rejected_without_execution(self):
        data=copy.deepcopy(DOC)
        node={"type":"string"}
        for _ in range(27):
            node={"items":node}
        data["components"]["schemas"]["Airframe"]=node
        with self.assertRaises(ResearchFormatError):
            inspect_openapi_graph(data)

    def test_oversized_request_media_map_rejected(self):
        data=copy.deepcopy(DOC)
        data["paths"]["/aircraft/{id}"]["post"]["requestBody"]["content"]={
            f"application/x-custom-{i}":{"schema":{"type":"string"}}
            for i in range(33)
        }
        with self.assertRaises(ResearchFormatError):
            inspect_openapi_graph(data)

    def test_external_schema_reference_is_not_dereferenced(self):
        data=copy.deepcopy(DOC)
        data["components"]["schemas"]={"External":{
            "$ref":"https://outside.example.net/private?api_key=SECRET"
        }}
        row=inspect_openapi_graph(data)
        self.assertEqual(row.declared_schema_count,1)
        self.assertEqual(row.ignored_external_references,1)
        self.assertEqual(row.local_schema_references,0)

    def test_local_dangling_schema_explicitly_unknown(self):
        report=inspect_openapi_graph(DOC)
        self.assertEqual(report.unresolved_local_references,1)
        self.assertTrue(report.topology_digest)
        self.assertTrue(any("unresolved local references: 1" in item
                            for item in summarize_openapi_graph(report)))

class Transport:
    timeout_seconds=4
    transport_mode="scripted_schema_graph"
    def __init__(self):
        self.calls=[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/schema":
            raise AssertionError("API source descriptor authorized unsolicited request")
        raw=json.dumps(DOC).encode()
        if len(raw)>max_bytes:
            raise AssertionError("scripted source exceeds reserved bytes")
        return FetchResponse(url,200,{"content-type":"application/openapi+json"},
                             raw,time.time())

class CanonicalCaptureTests(unittest.TestCase):
    def test_schema_graph_enters_original_unreviewed_source_receipt(self):
        now=time.time()
        fetcher=Transport()
        run=CrawlRun.create(
            CrawlRequest(seed_urls=("https://example.com/schema",),
                allowed_hosts=("example.com",),max_requests=4,max_documents=2,
                max_depth=1,max_response_bytes=65536,max_total_bytes=131072),
            scope={"tenant_id":"t","owner_id":"o"},
            consent={"consent_id":"api-graph-rights","capture_acknowledged":True,
                     "source_rights_acknowledged":True,"expires_at":now+3600},
            now=now,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                    cancelled=lambda:False,on_checkpoint=lambda snap,event:None)
        snap=run.snapshot()
        self.assertEqual(len(fetcher.calls),2)
        self.assertEqual(snap["usage"]["requests"],2)
        self.assertEqual(snap["usage"]["documents"],1)
        self.assertEqual(snap["frontier"],[])
        self.assertIn("Schema cycles: 1",run.sources()[0]["text"])
        self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
        self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
        self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap)

if __name__=="__main__":
    unittest.main()
