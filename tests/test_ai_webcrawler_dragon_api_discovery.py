"""Contract and canonical worker tests for scoped hypermedia API pagination.

External API documents nominate pagination URLs, never API method calls,
credentials, server-side actions, embedded authors, tracking beacons or
secondary transports. Snapshot replay remains byte/cost and consent bound.
"""
from __future__ import annotations
import json
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse
from skeleton.ai.webcrawler.api_discovery import (
    API_DISCOVERY_TYPES, APIDiscoveryError, discover_api_pages,
)
from skeleton.ai.webcrawler.structured_discovery import parse_structured_discovery
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com","archive.example"}))
URL = "https://example.com/api/articles"
EXTERNAL = "https://outside.example.net/private"

DOCUMENTS = {
    "application/vnd.api+json": {
        "jsonapi":{"version":"1.1"}, "data":[{"type":"article","id":"1",
          "relationships":{"author":{"links":{"next":EXTERNAL}}}}],
        "links":{"next":{"href":"/api/articles?page=2",
                         "meta":{"exec":"false"}},
                 "prev":"/api/articles?page=0",
                 "related":EXTERNAL},
    },
    "application/hal+json": {
        "_links":{"self":{"href":URL},"next":{"href":"?page=2"},
                  "prev":{"href":"?page=0"},"author":{"href":EXTERNAL}},
        "_embedded":{"articles":[{"_links":{"next":{"href":EXTERNAL}}}]},
    },
    "application/odata+json": {
        "@odata.context":"https://example.com/$metadata#articles",
        "value":[{"id":1,"action":{"url":EXTERNAL}}],
        "@odata.nextLink":"?page=2",
        "@odata.deltaLink":EXTERNAL,
    },
    "application/vnd.hydra+json": {
        "@context":"https://www.w3.org/ns/hydra/context.jsonld",
        "hydra:member":[{"@id":EXTERNAL}],
        "hydra:view":{"@type":"hydra:PartialCollectionView",
                      "hydra:next":"?page=2",
                      "hydra:previous":"?page=0",
                      "hydra:last":EXTERNAL},
    },
    "application/vnd.collection+json": {
        "collection":{"version":"1.0","href":URL,
          "items":[{"href":EXTERNAL}],
          "queries":[{"href":EXTERNAL,"rel":"search"}],
          "template":{"data":[{"name":"api_key","value":"SECRET"}]},
          "links":[{"href":"?page=2","rel":"next"},
                   {"href":"?page=0","rel":"prev"},
                   {"href":EXTERNAL,"rel":"alternate"}]},
    },
}


def parse(mime, value, *, max_links=16):
    return discover_api_pages(
        json.dumps(value).encode(), media_type=mime,
        document_url=URL, policy=POLICY, max_links=max_links,
    )


class APIContractTests(unittest.TestCase):
    def test_all_types_admit_only_top_level_page_links(self):
        for mime, doc in DOCUMENTS.items():
            with self.subTest(mime=mime):
                result=parse(mime,doc)
                self.assertEqual(result.links, (
                    "https://example.com/api/articles?page=2",
                    "https://example.com/api/articles?page=0",
                ) if mime!="application/odata+json" else (
                    "https://example.com/api/articles?page=2",
                ))
                self.assertTrue(result.pagination_only)
                self.assertFalse(result.acquired_network)
                self.assertFalse(result.added_authority)
                self.assertTrue(result.kind.endswith("_pagination"))
                self.assertNotIn(EXTERNAL,result.links)

    def test_canonical_policy_can_include_other_host_but_api_stays_same_origin(self):
        doc=DOCUMENTS["application/vnd.api+json"].copy()
        doc["links"]={"next":"https://archive.example/paged"}
        result=parse("application/vnd.api+json",doc)
        self.assertEqual(result.links,())
        self.assertEqual(result.rejected,1)

    def test_no_credentials_in_query_params(self):
        for query in ("?api_key=secret","?access_token=secret",
                      "?x-amz-signature=secret", "?client_secret=secret",
                      "?authorization=bearer", "?password=x",
                      "?private-credential=foo"):
            with self.subTest(query=query):
                doc={"data":[],"links":{"next":query}}
                result=parse("application/vnd.api+json",doc)
                self.assertEqual(result.links,())
                self.assertEqual(result.rejected,1)

    def test_duplicate_identical_links_deduplicated(self):
        doc={"data":[],"links":{"next":"?page=2","prev":"?page=2"}}
        result=parse("application/vnd.api+json",doc)
        self.assertEqual(len(result.links),1)
        self.assertEqual(result.rejected,1)

    def test_fractional_or_negative_query_is_still_source_data_not_a_grant(self):
        doc={"data":[],"links":{"next":"?cursor=next-19"}}
        result=parse("application/vnd.api+json",doc)
        self.assertEqual(result.links,("https://example.com/api/articles?cursor=next-19",))

    def test_link_capacity_has_explicit_truncation(self):
        doc=DOCUMENTS["application/vnd.api+json"]
        result=parse("application/vnd.api+json",doc,max_links=1)
        self.assertTrue(result.capped)
        self.assertEqual(len(result.links),1)

    def test_duplicate_json_keys_fail_closed(self):
        with self.assertRaises(APIDiscoveryError):
            discover_api_pages(
                b'{"data":[],"links":{"next":"?a=1","next":"?a=2"}}',
                media_type="application/vnd.api+json",
                document_url=URL,policy=POLICY,
            )

    def test_nonfinite_nested_number_fail_closed(self):
        with self.assertRaises(APIDiscoveryError):
            discover_api_pages(
                b'{"data":[{"score":NaN}],"links":{"next":"?page=2"}}',
                media_type="application/vnd.api+json",
                document_url=URL,policy=POLICY,
            )

    def test_malformed_document_root_denied(self):
        for mime in API_DISCOVERY_TYPES:
            with self.subTest(mime=mime):
                with self.assertRaises(APIDiscoveryError):
                    parse(mime,{"unrelated":"JSON document"})

    def test_oversized_api_document_denied(self):
        data={"data":[{"id":str(i)} for i in range(1025)],
              "links":{"next":"?page=2"}}
        with self.assertRaises(APIDiscoveryError):
            parse("application/vnd.api+json",data)

    def test_odata_delta_links_never_discovered(self):
        result=parse("application/odata+json",DOCUMENTS["application/odata+json"])
        self.assertEqual(len(result.links),1)
        self.assertEqual(result.links[0],URL+"?page=2")

    def test_only_mime_declared_api_root_interpreted_as_discovery(self):
        for mime,document in DOCUMENTS.items():
            with self.subTest(mime=mime):
                row=parse_structured_discovery(
                    json.dumps(document).encode(),
                    media_type=mime,document_url=URL,policy=POLICY,
                )
                self.assertEqual(row.links,parse(mime,document).links)
                self.assertFalse(row.new_authority_granted)
                self.assertFalse(row.source_text_retained)

    def test_non_utf8_and_binary_controls_denied(self):
        for body in (b"\xff\xfe",b"\x00",b'{"data":[],"links":{}}\xff'):
            with self.subTest(body=body),self.assertRaises(APIDiscoveryError):
                discover_api_pages(
                    body,media_type="application/vnd.api+json",
                    document_url=URL,policy=POLICY,
                )

    def test_password_userinfo_in_url_denied(self):
        doc={"data":[],"links":{"next":"https://user:pass@example.com/api"}}
        result=parse("application/vnd.api+json",doc)
        self.assertEqual(result.links,())
        self.assertEqual(result.rejected,1)


class ScriptedPaginationTransport:
    timeout_seconds=4
    transport_mode="scripted_canonical_json_hypermedia"
    def __init__(self,mime,data):
        self.mime,self.data,self.calls=mime,data,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(
                url,200,{"content-type":"text/plain"},
                b"User-agent: *\nAllow: /\n",time.time(),
            )
        if url!=URL:
            raise AssertionError("API page links requested prior to worker admission")
        body=json.dumps(self.data).encode()
        if len(body)>max_bytes:
            raise AssertionError("scripted transport exceeded byte reservation")
        return FetchResponse(
            url,200,{"content-type":self.mime},body,time.time(),
        )


class CanonicalAPIWorkerTests(unittest.TestCase):
    def capture(self,mime,document,*,extra_headers=None):
        now=time.time()
        fetcher=ScriptedPaginationTransport(mime,document)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=(URL,),allowed_hosts=("example.com","archive.example"),
                max_depth=1,max_requests=6,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"api-pagination-rights",
                     "capture_acknowledged":True,
                     "source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(
                    max_steps=1,max_seconds=1,
                    authorize=lambda:None,cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None,
                )
        return run,fetcher

    def test_all_api_types_enter_only_bounded_original_frontier(self):
        for mime,document in DOCUMENTS.items():
            with self.subTest(mime=mime):
                run,transport=self.capture(mime,document)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],0)
                self.assertEqual(len(transport.calls),2)
                self.assertEqual([x["url"] for x in state["frontier"]],list(
                    parse(mime,document).links,
                ))
                self.assertFalse(any(EXTERNAL in x["url"] for x in state["frontier"]))
                self.assertEqual(
                    CrawlRun.from_snapshot(state,fetcher=transport).snapshot(),
                    state,
                )

    def test_api_missing_schema_not_retained_as_opaque_source(self):
        run,transport=self.capture("application/hal+json",{"collection":1})
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(run.snapshot()["frontier"],[])
        self.assertEqual(len(transport.calls),2)

    def test_api_embedding_does_not_grant_authority(self):
        document={"data":[{"links":{"self":EXTERNAL,"next":EXTERNAL}}],
                  "links":{"next":"https://archive.example/other"}}
        run,transport=self.capture("application/vnd.api+json",document)
        self.assertEqual(run.snapshot()["frontier"],[])
        self.assertEqual(len(transport.calls),2)


if __name__=="__main__":
    unittest.main()
