"""Bounded OPDS, IIIF and OAI-PMH discovery through the actual CrawlRun."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse, extract_document
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun
from skeleton.ai.webcrawler.structured_discovery import (
    parse_structured_discovery, UnsupportedDiscoveryRoot, DiscoveryError,
)
from skeleton.ai.webcrawler.archive_catalog_common import CatalogDiscoveryError
from skeleton.ai.webcrawler.opds_discovery import discover_opds
from skeleton.ai.webcrawler.iiif_discovery import discover_iiif
from skeleton.ai.webcrawler.oai_pmh_discovery import discover_oai_pmh
from skeleton.ai.webcrawler.iiif_manifest_documents import extract_iiif_manifest
from skeleton.ai.webcrawler.research_projection import ResearchFormatError

ROOT = "https://example.com/catalog"
OAI = "https://example.com/oai?metadataPrefix=oai_dc&verb=ListIdentifiers"
IIIF = "https://example.com/iiif/collection"
MANIFEST = "https://example.com/iiif/manifest/flight"
OTHER = "https://outside.example.net/private"
POLICY = CrawlPolicy(allowed_hosts=frozenset({"example.com", "outside.example.net"}))
OPDS = {
    "metadata": {"title": "Flight research public catalog"},
    "links": [
        {"rel":"next","type":"application/opds+json","href":"/catalog?page=2"},
        {"rel":"prev","type":"application/opds+json","href":"/catalog?page=0"},
        {"rel":"subsection","type":"application/opds+json","href":"/subcatalog"},
        {"rel":"next","type":"application/opds+json","href":OTHER},
        {"rel":"acquisition","type":"application/epub+zip","href":OTHER},
    ],
    "navigation": [
        {"title":"Aerospace records","links":[
            {"type":"application/opds+json","href":"/aerospace/catalog"},
            {"type":"application/epub+zip","href":OTHER}
        ]}
    ],
    "publications": [
        {"metadata":{"title":"Aircraft stability studies"},
         "links":[{"rel":"http://opds-spec.org/acquisition",
                   "href":"https://example.com/books/secret.epub"}]}
    ]
}
IIIF_COLLECTION = {
    "@context":"http://iiif.io/api/presentation/3/context.json",
    "id":IIIF, "type":"Collection",
    "label":{"en":["Flight science"]},
    "items":[
        {"id":MANIFEST,"type":"Manifest"},
        {"id":"https://example.com/iiif/subcollection","type":"Collection"},
        {"id":OTHER,"type":"Manifest"},
        {"id":"https://example.com/iiif/canvas/1","type":"Canvas"},
    ],
    "next": "https://example.com/iiif/collection?page=2",
    "service":[{"id":OTHER,"type":"AuthCookieService1"}],
    "thumbnail":[{"id":OTHER,"type":"Image"}],
}
IIIF_MANIFEST = {
    "@context":"http://iiif.io/api/presentation/3/context.json",
    "id":MANIFEST, "type":"Manifest",
    "label":{"en":["Original flight studies"]},
    "summary":{"en":["Aviation and wing geometry research"]},
    "rights":"https://outside.example.net/not-a-license-grant",
    "items":[
        {"id":"https://example.com/iiif/canvas/1","type":"Canvas",
         "width":1600,"height":900,
         "items":[{"id":OTHER,"type":"AnnotationPage"}]},
        {"id":"https://example.com/iiif/canvas/2","type":"Canvas",
         "duration":120.0},
    ],
    "metadata":[{"label":{"en":["Category"]},"value":{"en":["Aerospace"]}}],
    "seeAlso":[{"id":OTHER,"type":"Dataset"}],
    "rendering":[{"id":OTHER,"type":"Video"}],
}


def oai_xml(token="cursor_A1b2c3"):
    cursor = (
        f"<resumptionToken cursor='0' completeListSize='7'>{token}</resumptionToken>"
        if token else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
        '<responseDate>2026-11-07T00:00:00Z</responseDate>'
        '<ListIdentifiers>'
        '<header><identifier>oai:example.com:flight001</identifier>'
        '<datestamp>2026-11-01</datestamp></header>'
        '<header><identifier>oai:example.com:flight002</identifier>'
        '<datestamp>2026-11-02</datestamp></header>'
        + cursor + '</ListIdentifiers></OAI-PMH>'
    ).encode()


class MalformedCatalogTypeTests(unittest.TestCase):
    def test_json_nonfinite_exponent_denied(self):
        from skeleton.ai.webcrawler.archive_catalog_common import load_json_catalog
        with self.assertRaises(CatalogDiscoveryError):
            load_json_catalog(b'{"metadata":{"title":"Sample"},"score":1e309}')

    def test_opds_mime_object_and_nested_link_container_denied(self):
        malformed = {**OPDS, "links": [{"rel": "next", "type": {"bad": "x"},
                                          "href": "/catalog?page=2"}]}
        with self.assertRaises(CatalogDiscoveryError):
            discover_opds(json.dumps(malformed).encode(), document_url=ROOT, policy=POLICY)
        malformed = {**OPDS, "navigation": [{"links": {"href": "/catalog"}}]}
        with self.assertRaises(CatalogDiscoveryError):
            discover_opds(json.dumps(malformed).encode(), document_url=ROOT, policy=POLICY)

    def test_iiif_unhashable_jsonld_context_and_item_types_denied_or_omitted(self):
        malformed = {**IIIF_COLLECTION, "@context": ["bad"]}
        with self.assertRaises(CatalogDiscoveryError):
            discover_iiif(json.dumps(malformed).encode(), document_url=IIIF, policy=POLICY)
        malformed = {**IIIF_COLLECTION, "items": [
            {"type": ["Manifest"], "id": MANIFEST},
            {"type": "Manifest", "id": MANIFEST},
        ]}
        row = discover_iiif(json.dumps(malformed).encode(), document_url=IIIF, policy=POLICY)
        self.assertEqual(row.links, (MANIFEST,
            "https://example.com/iiif/collection?page=2"))

    def test_iiif_manifest_wrong_context_type_and_infinite_duration_denied(self):
        bad = {**IIIF_MANIFEST, "@context": {"evil": "context"}}
        with self.assertRaises(ResearchFormatError):
            extract_iiif_manifest(json.dumps(bad))
        bad = json.loads(json.dumps(IIIF_MANIFEST))
        bad["items"][1]["duration"] = 1e309
        with self.assertRaises(ResearchFormatError):
            extract_iiif_manifest(json.dumps(bad))


class OPDSTests(unittest.TestCase):
    def test_navigation_without_ebook_downloads(self):
        row=discover_opds(json.dumps(OPDS).encode(),document_url=ROOT,policy=POLICY)
        self.assertEqual(row.links,(
            "https://example.com/catalog?page=2",
            "https://example.com/catalog?page=0",
            "https://example.com/subcatalog",
            "https://example.com/aerospace/catalog",
        ))
        self.assertFalse(row.network_executed)
        self.assertFalse(row.authority_granted)
        self.assertNotIn(OTHER,row.links)
        self.assertNotIn("https://example.com/books/secret.epub",row.links)

    def test_duplicate_json_keys_denied(self):
        raw=b'{"metadata":{"title":"A"},"links":[],"links":[]}'
        with self.assertRaises(CatalogDiscoveryError):
            discover_opds(raw,document_url=ROOT,policy=POLICY)

    def test_navigation_capacity_denied(self):
        doc={**OPDS,"navigation":[{"links":[]}]*257}
        with self.assertRaises(CatalogDiscoveryError):
            discover_opds(json.dumps(doc).encode(),document_url=ROOT,policy=POLICY)

    def test_invalid_missing_catalog_metadata_denied(self):
        with self.assertRaises(CatalogDiscoveryError):
            discover_opds(b'{"publications":[]}',document_url=ROOT,policy=POLICY)


class IIIFTests(unittest.TestCase):
    def test_collection_manifest_discovery_is_same_origin(self):
        row=discover_iiif(
            json.dumps(IIIF_COLLECTION).encode(),document_url=IIIF,policy=POLICY,
        )
        self.assertEqual(row.links,(
            MANIFEST,"https://example.com/iiif/subcollection",
            "https://example.com/iiif/collection?page=2",
        ))
        self.assertFalse(row.authority_granted)

    def test_manifest_is_retained_instead_of_traversing_image_services(self):
        with self.assertRaises(UnsupportedDiscoveryRoot):
            parse_structured_discovery(
                json.dumps(IIIF_MANIFEST).encode(),
                media_type="application/vnd.iiif.presentation+json",
                document_url=MANIFEST,policy=POLICY,
            )
        result=extract_iiif_manifest(json.dumps(IIIF_MANIFEST))
        self.assertIn("Original flight studies",result.text)
        self.assertIn("Canvas count: 2",result.text)
        self.assertIn("Dimensioned canvases: 1; timed canvases: 1",result.text)
        self.assertNotIn(OTHER,result.text)
        self.assertNotIn("not-a-license-grant",result.text)
        self.assertEqual(result.links,())
        self.assertFalse(result.body_executed)

    def test_invalid_canvas_geometry_denied(self):
        doc=json.loads(json.dumps(IIIF_MANIFEST))
        doc["items"][0]["width"]=999999999
        with self.assertRaises(ResearchFormatError):
            extract_iiif_manifest(json.dumps(doc))

    def test_external_jsonld_context_denied(self):
        with self.assertRaises(CatalogDiscoveryError):
            discover_iiif(json.dumps({**IIIF_COLLECTION,
                "@context":"https://outside.example.net/context"}).encode(),
                document_url=IIIF,policy=POLICY)


class OAITests(unittest.TestCase):
    def test_bounded_resumption_cursor_not_identifiers(self):
        row=discover_oai_pmh(oai_xml(),document_url=OAI,policy=POLICY)
        self.assertEqual(row.links,(
            "https://example.com/oai?resumptionToken=cursor_A1b2c3&verb=ListIdentifiers",
        ))
        self.assertNotIn("flight001",str(row))
        self.assertTrue(row.links_only)
        self.assertFalse(row.network_executed)

    def test_terminal_page_has_no_cursor(self):
        row=discover_oai_pmh(oai_xml(token=""),document_url=OAI,policy=POLICY)
        self.assertEqual(row.links,())

    def test_oai_external_entity_denied(self):
        blob=(b'<!DOCTYPE OAI-PMH [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'
              +oai_xml())
        with self.assertRaises(CatalogDiscoveryError):
            discover_oai_pmh(blob,document_url=OAI,policy=POLICY)

    def test_opaque_cursor_with_separators_denied(self):
        with self.assertRaises(CatalogDiscoveryError):
            discover_oai_pmh(oai_xml(token="secret&redirect=http://evil"),
                             document_url=OAI,policy=POLICY)

    def test_oai_incorrect_verb_denied(self):
        with self.assertRaises(CatalogDiscoveryError):
            discover_oai_pmh(oai_xml(),
                document_url="https://example.com/oai?verb=GetRecord",policy=POLICY)

    def test_oai_record_count_bounded(self):
        xml=oai_xml()
        row=b"<header><identifier>oai:x:y</identifier></header>"
        xml=xml.replace(b"<ListIdentifiers>",b"<ListIdentifiers>"+row*129)
        with self.assertRaises(CatalogDiscoveryError):
            discover_oai_pmh(xml,document_url=OAI,policy=POLICY)


class ScriptedCatalogFetcher:
    timeout_seconds=4
    transport_mode="scripted_archive_catalog"
    def __init__(self,url,mime,body):
        self.url,self.mime,self.body,self.calls=url,mime,body,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!=self.url:
            raise AssertionError("archive generated unapproved extra GET")
        if len(self.body)>max_bytes:
            raise AssertionError("archive payload exceeded reservation")
        return FetchResponse(url,200,{"content-type":self.mime},
                             self.body,time.time())


class CanonicalCatalogTests(unittest.TestCase):
    def capture(self,url,mime,body):
        now=time.time()
        fetcher=ScriptedCatalogFetcher(url,mime,body)
        run=CrawlRun.create(
            CrawlRequest(seed_urls=(url,),allowed_hosts=("example.com","outside.example.net"),
                max_depth=1,max_requests=5,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"public-archive-catalog",
                     "capture_acknowledged":True,"source_rights_acknowledged":True,
                     "expires_at":now+3600},
            now=now,fetcher=fetcher,
        )
        for delta in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=now+delta):
                run.run_slice(max_steps=1,max_seconds=1,
                    authorize=lambda:None,cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None)
        return run,fetcher

    def test_real_discovery_queues_only_allowed_public_catalog_links(self):
        fixtures=(
            (ROOT,"application/opds+json",json.dumps(OPDS).encode(),
             "https://example.com/subcatalog"),
            (IIIF,"application/vnd.iiif.presentation+json",
             json.dumps(IIIF_COLLECTION).encode(),MANIFEST),
            (OAI,"application/vnd.openarchives.oai-pmh+xml",oai_xml(),
             "https://example.com/oai?resumptionToken=cursor_A1b2c3&verb=ListIdentifiers"),
        )
        for url,mime,raw,expected in fixtures:
            with self.subTest(mime=mime):
                run,fetcher=self.capture(url,mime,raw)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],0)
                self.assertIn(expected,{x["url"] for x in state["frontier"]})
                self.assertFalse(any(OTHER in x["url"] for x in state["frontier"]))
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(CrawlRun.from_snapshot(
                    state,fetcher=fetcher).snapshot(),state)

    def test_iiif_manifest_is_a_real_retained_source(self):
        run,fetcher=self.capture(
            MANIFEST,"application/vnd.iiif.presentation+json",
            json.dumps(IIIF_MANIFEST).encode(),
        )
        state=run.snapshot()
        self.assertEqual(state["usage"]["requests"],2)
        self.assertEqual(state["usage"]["documents"],1)
        self.assertEqual(state["frontier"],[])
        self.assertIn("Original flight studies",run.sources()[0]["text"])
        self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
        self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
        self.assertEqual(CrawlRun.from_snapshot(
            state,fetcher=fetcher).snapshot(),state)

    def test_malformed_oai_never_publishes_source(self):
        run,fetcher=self.capture(
            OAI,"application/vnd.openarchives.oai-pmh+xml",
            b'<OAI-PMH><error code="badVerb">error</error></OAI-PMH>',
        )
        self.assertEqual(run.snapshot()["usage"]["requests"],2)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(run.snapshot()["frontier"],[])
        self.assertEqual(len(fetcher.calls),2)

    def test_media_types_are_explicit(self):
        allow=POLICY.allowed_content_types
        for mime in ("application/opds+json",
                     "application/vnd.iiif.presentation+json",
                     "application/vnd.openarchives.oai-pmh+xml"):
            self.assertIn(mime,allow)


if __name__=="__main__":
    unittest.main()
