"""Finite GraphQL/AsyncAPI/proto3 source topology and canonical replay."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.graphql_documents import extract_graphql_schema
from skeleton.ai.webcrawler.asyncapi_documents import extract_asyncapi
from skeleton.ai.webcrawler.proto_documents import extract_proto
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun

def typ(name,kind="OBJECT",fields=None):
    return {"kind":kind,"name":name,"fields":fields or []}

def field(name,of):
    return {"name":name,"type":{"kind":"OBJECT","name":of},"args":[]}

GRAPHQL=json.dumps({
    "data":{"__schema":{
        "queryType":{"name":"Query"},"mutationType":{"name":"Mutation"},
        "subscriptionType":None,
        "types":[
            typ("Query",fields=[field("flight","Flight")]),
            typ("Mutation",fields=[field("change","Flight")]),
            typ("Flight",fields=[field("wing","Wing")]),
            typ("Wing",fields=[field("flight","Flight")]),
            typ("String","SCALAR"),
        ]
    }},
    "extensions":{"credential":"SECRET_GRAPHQL","url":"https://outside.example.net/graphql"},
})
ASYNC2=json.dumps({
    "asyncapi":"2.6.0",
    "info":{"title":"Flight event bus"},
    "servers":{"prod":{"url":"wss://outside.example.net/SECRET_BROKER"}},
    "channels":{"flights.changed":{
        "publish":{"message":{"$ref":"#/components/messages/Flight"}},
        "subscribe":{"message":{"$ref":"#/components/messages/Unknown"}},
    }},
    "components":{"messages":{"Flight":{"name":"Flight","payload":{"type":"object"}}}},
})
ASYNC3=json.dumps({
    "asyncapi":"3.0.0",
    "channels":{"flightChange":{"messages":{"flight":{"$ref":"#/components/messages/Flight"}}}},
    "operations":{"sendFlight":{
        "action":"send","channel":{"$ref":"#/channels/flightChange"},
        "messages":[{"$ref":"#/components/messages/Flight"}],
    }},
    "components":{"messages":{"Flight":{"payload":{"type":"object"}}}},
})
PROTO='''syntax = "proto3";
package original.flight;
import "https://outside.example.net/SECRET_PROTO";
message Flight {
  string name = 1;
}
message Wing {
  int32 length = 1;
}
enum FlightMode {
  UNDEFINED = 0;
  GLIDE = 1;
}
service FlightService {
  rpc BuildWorld (Flight) returns (Wing);
}
'''

class GraphQLTests(unittest.TestCase):
    def test_type_dependencies_impact_and_cycles(self):
        row=extract_graphql_schema(GRAPHQL)
        self.assertIn("Declared types: 5",row.text)
        self.assertIn("Strong cyclic type groups: 1",row.text)
        self.assertIn("cycle member types: 2",row.text)
        self.assertIn("query, mutation",row.text)
        self.assertNotIn("SECRET_GRAPHQL",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertEqual(row.links,())
        self.assertFalse(row.reference_trusted)

    def test_duplicate_key_and_missing_root_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_graphql_schema('{"data":{"__schema":{}},"data":{"__schema":{}}}')
        with self.assertRaises(ResearchFormatError):
            extract_graphql_schema('{"data":{}}')

    def test_unbounded_field_types_denied(self):
        source=json.loads(GRAPHQL)
        source["data"]["__schema"]["types"][0]["fields"]=[field("field","Wing")]*129
        with self.assertRaises(ResearchFormatError):
            extract_graphql_schema(json.dumps(source))

    def test_unsupported_nested_ref_depth_denied(self):
        source=json.loads(GRAPHQL)
        root={"kind":"OBJECT","name":"Flight"}
        for _ in range(13):
            root={"kind":"NON_NULL","ofType":root}
        source["data"]["__schema"]["types"][0]["fields"][0]["type"]=root
        with self.assertRaises(ResearchFormatError):
            extract_graphql_schema(json.dumps(source))

    def test_graphql_missing_root_identity_denied(self):
        source=json.loads(GRAPHQL)
        source["data"]["__schema"]["queryType"]={"name":"SecretService"}
        with self.assertRaises(ResearchFormatError):
            extract_graphql_schema(json.dumps(source))

class AsyncAPITests(unittest.TestCase):
    def test_2_6_event_contract_not_broker_operation(self):
        row=extract_asyncapi(ASYNC2)
        self.assertIn("Channels: 1; declared messages: 1",row.text)
        self.assertIn("Declared event operations: 2",row.text)
        self.assertIn("resolved",row.text.lower())
        self.assertNotIn("SECRET_BROKER",row.text)
        self.assertFalse(row.body_executed)
        self.assertEqual(row.links,())

    def test_3_0_channels_actions(self):
        row=extract_asyncapi(ASYNC3)
        self.assertIn("send=1",row.text)
        self.assertIn("resolved",row.text.lower())
        self.assertEqual(row.links,())

    def test_invalid_action_and_many_channels_denied(self):
        source=json.loads(ASYNC3)
        source["operations"]["sendFlight"]["action"]="execute"
        with self.assertRaises(ResearchFormatError):
            extract_asyncapi(json.dumps(source))
        source=json.loads(ASYNC2)
        source["channels"]={f"channel-{i}":{} for i in range(257)}
        with self.assertRaises(ResearchFormatError):
            extract_asyncapi(json.dumps(source))

    def test_asyncapi_does_not_expand_external_contexts(self):
        source=json.loads(ASYNC3)
        source["operations"]["sendFlight"]["channel"]["$ref"]="https://outside.example.net/broker"
        row=extract_asyncapi(json.dumps(source))
        self.assertIn("unresolved/remote references ignored: 1",row.text)
        self.assertNotIn("outside.example.net",row.text)

class ProtoTests(unittest.TestCase):
    def test_proto3_declarations_and_unresolved_import(self):
        row=extract_proto(PROTO)
        self.assertIn("Messages: 2; enums: 1; services: 1; RPC declarations: 1",row.text)
        self.assertIn("Declared package: original.flight",row.text)
        self.assertIn("BuildWorld",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertNotIn("SECRET_PROTO",row.text)
        self.assertFalse(row.body_executed)
        self.assertEqual(row.links,())

    def test_proto2_is_not_silently_accepted(self):
        with self.assertRaises(ResearchFormatError):
            extract_proto(PROTO.replace('"proto3"','"proto2"'))

    def test_unclosed_rpc_service_and_bad_brace_refused(self):
        with self.assertRaises(ResearchFormatError):
            extract_proto(PROTO.rsplit("}",1)[0])
        with self.assertRaises(ResearchFormatError):
            extract_proto(PROTO+"}\n")

    def test_unbounded_line_or_imports_refused(self):
        with self.assertRaises(ResearchFormatError):
            extract_proto(PROTO+'import "not-verified.proto";\n'*65)

class Transport:
    timeout_seconds=4
    transport_mode="scripted_interface_contracts"
    def __init__(self,mime,data):
        self.mime,self.body,self.calls=mime,data.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/interface":
            raise AssertionError("external interface description attempted network IO")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())

class CanonicalInterfaceTests(unittest.TestCase):
    def test_all_three_interface_families_use_original_worker(self):
        for mime,raw,marker in (
            ("application/vnd.graphql.introspection+json",GRAPHQL,"GraphQL"),
            ("application/vnd.asyncapi+json",ASYNC2,"Channels: 1"),
            ("application/asyncapi+json",ASYNC3,"send=1"),
            ("text/x-protobuf",PROTO,"BuildWorld"),
        ):
            with self.subTest(mime=mime):
                at=time.time()
                fetcher=Transport(mime,raw)
                run=CrawlRun.create(
                    CrawlRequest(
                        seed_urls=("https://example.com/interface",),
                        allowed_hosts=("example.com",),max_depth=1,
                        max_requests=4,max_documents=2,
                        max_response_bytes=65536,max_total_bytes=131072,
                    ),
                    scope={"tenant_id":"t","owner_id":"o"},
                    consent={"consent_id":"interface-capture-rights",
                             "capture_acknowledged":True,
                             "source_rights_acknowledged":True,"expires_at":at+3600},
                    now=at,fetcher=fetcher,
                )
                for offset in (1,3):
                    with patch("skeleton.ai.webcrawler.operations.time.time",return_value=at+offset):
                        run.run_slice(max_steps=1,max_seconds=1,
                            authorize=lambda:None,cancelled=lambda:False,
                            on_checkpoint=lambda snap,event:None)
                state=run.snapshot()
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(state["frontier"],[])
                self.assertIn(marker,run.sources()[0]["text"])
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
                self.assertEqual(CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),state)

    def test_mime_policy_closed(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("application/vnd.graphql.introspection+json",
                     "application/vnd.asyncapi+json","text/x-protobuf"):
            self.assertIn(mime,allowed)
        self.assertNotIn("application/x-msdownload",allowed)

if __name__=="__main__":
    unittest.main()
