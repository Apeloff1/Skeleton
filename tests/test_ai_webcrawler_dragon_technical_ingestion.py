"""GeoJSON, OpenAPI, JSON Schema and TSV through canonical bounded crawling."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.core import FetchResponse, CrawlPolicy
from skeleton.ai.webcrawler.operations import CrawlRun, CrawlRequest
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.geojson_documents import extract_geojson
from skeleton.ai.webcrawler.openapi_documents import extract_openapi
from skeleton.ai.webcrawler.jsonschema_documents import extract_jsonschema
from skeleton.ai.webcrawler.tsv_documents import extract_tsv

GEO = json.dumps({
    "type":"FeatureCollection",
    "features":[
        {"type":"Feature",
         "geometry":{"type":"LineString",
                     "coordinates":[[5.12345,59.33111],[5.23455,59.44122]]},
         "properties":{"name":"Aviation research route",
                       "description":"Scenic navigation across modeled terrain",
                       "api_key":"SECRET_GEO_TOKEN",
                       "url":"https://outside.example.net/private"}},
        {"type":"Feature",
         "geometry":{"type":"Point","coordinates":[5.1,59.31]},
         "properties":{"category":"Aeronautical waypoint"}}
    ],
})
OPENAPI = json.dumps({
    "openapi":"3.1.0",
    "info":{"title":"Aviation simulation API"},
    "servers":[{"url":"https://outside.example.net/private?secret=SERVER_SECRET"}],
    "security":[{"BearerAuth":[]}],
    "components":{"securitySchemes":{"BearerAuth":{"type":"http","scheme":"bearer"}}},
    "paths":{
        "/aircraft/{id}":{"get":{
            "summary":"Read aircraft stability profile",
            "operationId":"readAircraft",
            "responses":{"200":{"description":"The source profile"},"404":{"description":"Missing"}},
            "security":[{"BearerAuth":[]}],
            "requestBody":{"content":{"text/plain":{"example":"SECRET_EXAMPLE"}}}
        }},
        "/flight":{"post":{
            "summary":"Propose a flight configuration",
            "operationId":"proposeFlight",
            "responses":{"201":{"description":"Created"}},
        }},
        "/ignored":{"$ref":"https://outside.example.net/schema.json"}
    }
})
SCHEMA = json.dumps({
    "$schema":"https://json-schema.org/draft/2020-12/schema",
    "title":"Flight profile schema",
    "type":"object",
    "properties":{
        "flight_mode":{"type":"string","description":"Engine traversal profile",
                       "default":"SECRET_DEFAULT"},
        "wind_speed":{"type":"number","description":"Wind speed in meters per second"},
        "flight_modes":{"type":["array","null"]},
    },
    "required":["flight_mode"],
    "$defs":{"secret":{"$ref":"https://outside.example.net/unknown.json"}},
})
TSV = "name\tcategory\tvalue\nFlight archive\tdocument\t15\nAviation\tmodel\t=HYPERLINK('https://outside.example.net')"


class GeometryTests(unittest.TestCase):
    def test_geojson_precise_points_coarsened(self):
        result=extract_geojson(GEO)
        self.assertIn("Aviation research route",result.text)
        self.assertIn("LineString",result.text)
        self.assertIn("bounds_approx:",result.text)
        self.assertNotIn("5.12345",result.text)
        self.assertNotIn("outside.example.net",result.text)
        self.assertNotIn("SECRET_GEO_TOKEN",result.text)
        self.assertEqual(result.links,())

    def test_geojson_rejects_nonfinite(self):
        with self.assertRaises(ResearchFormatError):
            extract_geojson('{"type":"Point","coordinates":[NaN,0]}')

    def test_geojson_rejects_out_of_range(self):
        with self.assertRaises(ResearchFormatError):
            extract_geojson('{"type":"Point","coordinates":[190,0]}')

    def test_geojson_rejects_oversized_feature_count(self):
        sample={"type":"FeatureCollection",
                "features":[{"type":"Feature","geometry":{"type":"Point",
                             "coordinates":[0,0]},"properties":{}}]*257}
        with self.assertRaises(ResearchFormatError):
            extract_geojson(json.dumps(sample))

    def test_geojson_rejects_oversized_coordinates(self):
        sample={"type":"LineString","coordinates":[[0,0]]*32769}
        with self.assertRaises(ResearchFormatError):
            extract_geojson(json.dumps(sample))


class OpenAPITests(unittest.TestCase):
    def test_openapi_captures_operations_not_secrets(self):
        row=extract_openapi(OPENAPI)
        self.assertIn("Aviation simulation API",row.title)
        self.assertIn("GET /aircraft/{id}",row.text)
        self.assertIn("POST /flight",row.text)
        self.assertIn("200,404",row.text)
        self.assertNotIn("outside.example.net",row.text)
        self.assertNotIn("SERVER_SECRET",row.text)
        self.assertNotIn("SECRET_EXAMPLE",row.text)
        self.assertEqual(row.links,())

    def test_openapi_wrong_version_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_openapi('{"openapi":"2.0","paths":{"/x":{"get":{}}}}')

    def test_openapi_external_path_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_openapi('{"openapi":"3.1","paths":{"https://evil/x":{"get":{}}}}')

    def test_openapi_malformed_responses_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_openapi('{"openapi":"3.1","paths":{"/x":{"get":{"responses":[]}}}}')


class JSONSchemaTests(unittest.TestCase):
    def test_jsonschema_property_labels_not_secrets(self):
        result=extract_jsonschema(SCHEMA)
        self.assertIn("Flight profile schema",result.title)
        self.assertIn("Schema field flight_mode",result.text)
        self.assertIn("required: True",result.text)
        self.assertIn("array|null",result.text)
        self.assertNotIn("SECRET_DEFAULT",result.text)
        self.assertNotIn("outside.example.net",result.text)
        self.assertEqual(result.links,())

    def test_invalid_property_types_not_evaluated(self):
        result=extract_jsonschema('{"properties":{"file":{"$ref":"https://evil/x"}}}')
        self.assertIn("unspecified",result.text)
        self.assertNotIn("evil",result.text)

    def test_nonfinite_rejected(self):
        with self.assertRaises(ResearchFormatError):
            extract_jsonschema('{"properties":{"p":{"type":"number","default":Infinity}}}')

    def test_oversized_schema_field_count_denied(self):
        data={"properties":{f"p{i}":{"type":"string"} for i in range(257)}}
        with self.assertRaises(ResearchFormatError):
            extract_jsonschema(json.dumps(data))


class TSVTests(unittest.TestCase):
    def test_tsv_finite_rows_no_formula_execution(self):
        result=extract_tsv(TSV)
        self.assertIn("Flight archive",result.text)
        self.assertIn("HYPERLINK",result.text)
        self.assertFalse(result.body_executed)
        self.assertEqual(result.links,())

    def test_tsv_malformed_quote_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_tsv("a\tb\n1\t\"bad")

    def test_tsv_width_mismatch_denied(self):
        with self.assertRaises(ResearchFormatError):
            extract_tsv("a\tb\n1")


class FakeTransport:
    timeout_seconds=4
    transport_mode="scripted_technical_evidence"
    def __init__(self,mime,payload):
        self.mime,self.payload,self.calls=mime,payload,[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/technical":
            raise AssertionError("technical source attempted unsolicited navigation")
        if len(self.payload)>max_bytes:
            raise AssertionError("mock source would exceed reserved cap")
        return FetchResponse(url,200,{"content-type":self.mime},self.payload,time.time())


class CanonicalTechnicalTests(unittest.TestCase):
    def run_source(self,mime,text):
        now=time.time()
        fetcher=FakeTransport(mime,text.encode())
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/technical",),
                allowed_hosts=("example.com",),
                max_depth=1,max_requests=4,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"technical-rights","capture_acknowledged":True,
                     "source_rights_acknowledged":True,"expires_at":now+3600},
            now=now,fetcher=fetcher,
        )
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",
                       return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,authorize=lambda:None,
                              cancelled=lambda:False,
                              on_checkpoint=lambda snapshot,event:None)
        return run,fetcher

    def test_all_formats_capture_under_real_canonical_run(self):
        cases=(
            ("application/geo+json",GEO,"Aviation research route"),
            ("application/openapi+json",OPENAPI,"GET /aircraft/{id}"),
            ("application/schema+json",SCHEMA,"flight_mode"),
            ("text/tab-separated-values",TSV,"Flight archive"),
        )
        for mime,raw,expected in cases:
            with self.subTest(mime=mime):
                run,fetcher=self.run_source(mime,raw)
                snapshot=run.snapshot()
                self.assertEqual(snapshot["usage"]["documents"],1)
                self.assertEqual(snapshot["usage"]["requests"],2)
                self.assertEqual(len(fetcher.calls),2)
                self.assertEqual(snapshot["frontier"],[])
                self.assertIn(expected,run.sources()[0]["text"])
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertEqual(
                    CrawlRun.from_snapshot(snapshot,fetcher=fetcher).snapshot(),
                    snapshot,
                )

    def test_invalid_geojson_charges_attempt_without_source(self):
        run,fetcher=self.run_source(
            "application/geo+json",
            '{"type":"Point","coordinates":[999,0]}',
        )
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)

    def test_media_types_are_explicit_and_closed(self):
        allow=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime in ("application/geo+json","application/openapi+json",
                     "application/schema+json","text/tab-separated-values"):
            self.assertIn(mime,allow)


if __name__=="__main__":
    unittest.main()
