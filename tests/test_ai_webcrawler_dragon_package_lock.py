"""Four bounded package-lock families via direct and canonical source capture."""
from __future__ import annotations
import json
import time
import unittest
from unittest.mock import patch
from skeleton.ai.webcrawler.npm_lock_documents import extract_npm_lock
from skeleton.ai.webcrawler.cargo_lock_documents import extract_cargo_lock
from skeleton.ai.webcrawler.go_mod_documents import extract_go_mod
from skeleton.ai.webcrawler.pylock_documents import extract_pylock
from skeleton.ai.webcrawler.research_projection import ResearchFormatError
from skeleton.ai.webcrawler.core import CrawlPolicy,FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest,CrawlRun

NPM=json.dumps({"name":"flight-world","lockfileVersion":3,
    "packages":{
        "":{"name":"flight-world","version":"1","dependencies":{"wing":"1","solver":"2"}},
        "node_modules/wing":{"name":"wing","version":"1"},
        "node_modules/solver":{"name":"solver","version":"2","integrity":"SECRET_HASH",
            "resolved":"https://outside.example.net/SECRET_URL","dependencies":{"wing":"1"}},
    },"scripts":{"postinstall":"https://outside.example.net/run"}})
CARGO='''version = 4
[[package]]
name = "world"
version = "1.0.0"
dependencies = ["physics 2.1.0", "scene 1.0.0"]
[[package]]
name = "physics"
version = "2.1.0"
checksum = "SECRET_HASH"
dependencies = ["scene 1.0.0"]
[[package]]
name = "scene"
version = "1.0.0"
'''
GO='''module example.com/original-game
go 1.24
require (
example.org/wing v1.2.3
example.org/flight v2.0.0
)
replace example.org/flight => https://outside.example.net/secret
'''
PYLOCK='''lock-version = "1.0"
[[packages]]
name = "airframe"
version = "1.0"
dependencies = [{name = "worldgraph"}]
[[packages]]
name = "worldgraph"
version = "2.0"
[packages.sdist]
url = "https://outside.example.net/secret-download"
'''
SAMPLES=(
    ("application/vnd.npm.package-lock+json",NPM,extract_npm_lock,"Components: 3; dependencies: 3"),
    ("application/vnd.cargo.lock+toml",CARGO,extract_cargo_lock,"Components: 3; dependencies: 3"),
    ("text/x-go-mod",GO,extract_go_mod,"Components: 3; dependencies: 2"),
    ("text/x-pylock",PYLOCK,extract_pylock,"Components: 2; dependencies: 1"),
)

class ParserTests(unittest.TestCase):
    def test_graphs_are_real_and_never_dereference(self):
        for mime,raw,parser,marker in SAMPLES:
            with self.subTest(mime=mime):
                row=parser(raw)
                self.assertIn(marker,row.text)
                self.assertEqual(row.links,())
                self.assertFalse(row.body_executed)
                self.assertFalse(row.reference_trusted)
                self.assertNotIn("outside.example.net",row.text)
                self.assertNotIn("SECRET_HASH",row.text)
    def test_npm_traversal_and_capacity(self):
        bad=json.loads(NPM)
        bad["packages"]["../private"]={"name":"private"}
        with self.assertRaises(ResearchFormatError):
            extract_npm_lock(json.dumps(bad))
        bad={"lockfileVersion":3,"packages":{
            f"node_modules/lib-{i}":{"version":"1"} for i in range(257)}}
        with self.assertRaises(ResearchFormatError):
            extract_npm_lock(json.dumps(bad))
    def test_json_duplicate_keys(self):
        with self.assertRaises(ResearchFormatError):
            extract_npm_lock('{"lockfileVersion":3,"packages":{},"packages":{}}')
    def test_cargo_duplicate_toml_and_unsupported_version(self):
        with self.assertRaises(ResearchFormatError):
            extract_cargo_lock(CARGO.replace("version = 4","version = 8",1))
        with self.assertRaises(ResearchFormatError):
            extract_cargo_lock("version = 4\nversion = 3\n"+CARGO)
    def test_go_conflict_and_invalid_versions(self):
        with self.assertRaises(ResearchFormatError):
            extract_go_mod(GO.replace("v1.2.3","1.2.3"))
        with self.assertRaises(ResearchFormatError):
            extract_go_mod(GO.replace("example.org/wing v1.2.3",
                "example.org/wing v1.2.3\nexample.org/wing v9.0.0"))
    def test_pylock_version_and_bad_dependency(self):
        with self.assertRaises(ResearchFormatError):
            extract_pylock(PYLOCK.replace('lock-version = "1.0"',
                                          'lock-version = "8.0"'))
        with self.assertRaises(ResearchFormatError):
            extract_pylock(PYLOCK.replace('name = "worldgraph"}',
                                          'name = 123}'))

class Transport:
    timeout_seconds=4
    transport_mode="scripted_package_lock"
    def __init__(self,mime,text):
        self.mime,self.body,self.calls=mime,text.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(url,200,{"content-type":"text/plain"},
                                 b"User-agent: *\nAllow: /\n",time.time())
        if url!="https://example.com/software":
            raise AssertionError("manifest induced external package request")
        return FetchResponse(url,200,{"content-type":self.mime},self.body,time.time())

class CanonicalSourceTests(unittest.TestCase):
    def capture(self,mime,text):
        now=time.time()
        fetcher=Transport(mime,text)
        run=CrawlRun.create(
            CrawlRequest(seed_urls=("https://example.com/software",),
                allowed_hosts=("example.com",),max_requests=4,max_documents=2,
                max_depth=1,max_response_bytes=65536,max_total_bytes=131072),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"package-lock-rights",
                "capture_acknowledged":True,"source_rights_acknowledged":True,
                "expires_at":now+3600},
            now=now,fetcher=fetcher)
        for offset in (1,3):
            with patch("skeleton.ai.webcrawler.operations.time.time",return_value=now+offset):
                run.run_slice(max_steps=1,max_seconds=1,
                    authorize=lambda:None,cancelled=lambda:False,
                    on_checkpoint=lambda snapshot,event:None)
        return run,fetcher
    def test_all_four_types_capture_and_replay(self):
        for mime,raw,parser,marker in SAMPLES:
            with self.subTest(mime=mime):
                run,fetcher=self.capture(mime,raw)
                snap=run.snapshot()
                self.assertEqual(snap["usage"]["requests"],2)
                self.assertEqual(snap["usage"]["documents"],1)
                self.assertEqual(snap["frontier"],[])
                self.assertEqual(len(fetcher.calls),2)
                self.assertIn(marker,run.sources()[0]["text"])
                self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertEqual(CrawlRun.from_snapshot(snap,fetcher=fetcher).snapshot(),snap)
    def test_invalid_source_charged_not_retained(self):
        run,fetcher=self.capture("application/vnd.npm.package-lock+json","{}")
        self.assertEqual(run.snapshot()["usage"]["requests"],2)
        self.assertEqual(run.snapshot()["usage"]["documents"],0)
        self.assertEqual(len(fetcher.calls),2)
    def test_types_explicit(self):
        allowed=CrawlPolicy(allowed_hosts=frozenset({"example.com"})).allowed_content_types
        for mime,*_ in SAMPLES:
            self.assertIn(mime,allowed)

if __name__=="__main__":
    unittest.main()
