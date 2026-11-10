"""Finite AST/lexical structural source intelligence and canonical acquisition."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from skeleton.ai.webcrawler.python_signatures import extract_python_signatures
from skeleton.ai.webcrawler.lexical_signatures import extract_lexical_signatures
from skeleton.ai.webcrawler.source_signatures import SourceSignatureError
from skeleton.ai.webcrawler.source_structure import analyze_source_structure
from skeleton.ai.webcrawler.core import FetchResponse
from skeleton.ai.webcrawler.operations import CrawlRequest, CrawlRun

PYTHON = (
    "import math\nfrom dataclasses import dataclass\n"
    "SECRET_PASSWORD = 'not a declaration'\n"
    "@dataclass\nclass FlightEngine:\n"
    "    def lift(self, angle: float, speed: float):\n"
    "        return angle + speed\n"
    "    async def simulate(self, terrain):\n"
    "        return self.lift(terrain, 2)\n"
    "def build_scene(graph, state):\n"
    "    return FlightEngine()\n"
)
JS = (
    "// function FalseDefinition(x) {}\n"
    "const literal = 'class FakeClass {}';\n"
    "export class DragonBuilder {}\n"
    "export function buildWorld(seed) {}\n"
    "export const runGame = (seed) => seed;\n"
    "/* class CommentClass {} */\n"
)
RUST = (
    "// fn false_definition() {}\n"
    "pub struct WorldGraph { nodes: usize }\n"
    "pub enum WorldEvent { Spawn, Despawn }\n"
    "pub async fn construct_world(seed: u64) {}\n"
    "use core::fmt;\n"
)
GO = (
    "package dragon\n"
    "type World struct { Nodes int }\n"
    "func (w *World) Build(seed int) {}\n"
    "func RenderWorld() {}\n"
)
CPP = (
    "// class FakeClass {}\n"
    "class GeometryEngine { };\n"
    "static int geometry_count(int width) { return width; }\n"
)


class PythonASTTests(unittest.TestCase):
    def test_definitions_are_qualified_and_params_are_finite(self):
        signatures = extract_python_signatures(PYTHON)
        names = {(x.kind,x.symbol,x.arity) for x in signatures.declarations}
        self.assertIn(("class","FlightEngine",None),names)
        self.assertIn(("function","FlightEngine.lift",3),names)
        self.assertIn(("async_function","FlightEngine.simulate",2),names)
        self.assertIn(("function","build_scene",2),names)
        self.assertIn("math",signatures.imports)
        self.assertIn("dataclasses",signatures.imports)
        self.assertFalse(signatures.source_executed)
        self.assertFalse(signatures.references_fetched)
        self.assertFalse(signatures.approximate)

    def test_literal_secrets_never_enter_ast_projection(self):
        row = analyze_source_structure(PYTHON,"text/x-python")
        self.assertIn("FlightEngine.simulate",row.text)
        self.assertNotIn("SECRET_PASSWORD",row.text)
        self.assertNotIn("not a declaration",row.text)
        self.assertTrue(row.syntax_validated)
        self.assertFalse(row.body_executed)
        self.assertFalse(row.code_approved)

    def test_invalid_python_syntax_not_misrepresented(self):
        with self.assertRaises(SourceSignatureError):
            extract_python_signatures("def broken(\n pass")

    def test_source_expansion_guard(self):
        with self.assertRaises(SourceSignatureError):
            extract_python_signatures("x = 1\n"*40000)

    def test_binary_control_rejected(self):
        with self.assertRaises(SourceSignatureError):
            extract_python_signatures("import os\x00")

    def test_duplicate_nested_names_are_distinct(self):
        src = "class One:\n def run(self): pass\nclass Two:\n def run(self): pass\n"
        result=extract_python_signatures(src)
        self.assertIn("One.run",[x.symbol for x in result.declarations])
        self.assertIn("Two.run",[x.symbol for x in result.declarations])


class LexicalSourceTests(unittest.TestCase):
    def test_javascript_class_function_and_arrow(self):
        row=extract_lexical_signatures(JS,"javascript")
        labels={(x.kind,x.symbol) for x in row.declarations}
        self.assertIn(("class","DragonBuilder"),labels)
        self.assertIn(("function","buildWorld"),labels)
        self.assertIn(("arrow_function","runGame"),labels)
        self.assertNotIn(("function","FalseDefinition"),labels)
        self.assertNotIn(("class","FakeClass"),labels)
        self.assertNotIn(("class","CommentClass"),labels)
        self.assertTrue(row.approximate)
        self.assertFalse(row.source_executed)

    def test_rust_struct_enum_async_function(self):
        row=extract_lexical_signatures(RUST,"rust")
        kinds={(x.kind,x.symbol) for x in row.declarations}
        self.assertIn(("struct","WorldGraph"),kinds)
        self.assertIn(("enum","WorldEvent"),kinds)
        self.assertIn(("fn","construct_world"),kinds)
        self.assertIn("core::fmt",row.imports)

    def test_go_receivers_and_free_functions(self):
        row=extract_lexical_signatures(GO,"go")
        found={(x.kind,x.symbol) for x in row.declarations}
        self.assertIn(("struct","World"),found)
        self.assertIn(("function","Build"),found)
        self.assertIn(("function","RenderWorld"),found)

    def test_cxx_class_and_callable_are_lexical_candidates(self):
        row=extract_lexical_signatures(CPP,"cpp")
        self.assertTrue(row.approximate)
        self.assertIn(("type","GeometryEngine"),
                      {(x.kind,x.symbol) for x in row.declarations})

    def test_unknown_language_rejected(self):
        with self.assertRaises(SourceSignatureError):
            extract_lexical_signatures("function test() {}","not-executable")

    def test_malicious_quoted_fake_function_is_not_declared(self):
        row=extract_lexical_signatures(
            "const code = \"function evil() {}\";\n"
            "// function secret() {}\n"
            "function safe() {}\n","typescript",
        )
        names={x.symbol for x in row.declarations}
        self.assertEqual(names,{"safe"})


class ScriptedSourceTransport:
    timeout_seconds=4
    transport_mode="scripted_source_structure_canonical"
    def __init__(self,mime,source):
        self.mime,self.source,self.calls=mime,source.encode(),[]
    def fetch_once(self,url,*,user_agent,max_bytes):
        self.calls.append(url)
        if url=="https://example.com/robots.txt":
            return FetchResponse(
                url,200,{"content-type":"text/plain"},
                b"User-agent: *\nAllow: /\n",time.time(),
            )
        if url!="https://example.com/code":
            raise AssertionError("source import reference attempted external fetch")
        return FetchResponse(
            url,200,{"content-type":self.mime},
            self.source,time.time(),
        )


class CanonicalSourceTests(unittest.TestCase):
    def capture(self,mime,source):
        now=time.time()
        fetcher=ScriptedSourceTransport(mime,source)
        run=CrawlRun.create(
            CrawlRequest(
                seed_urls=("https://example.com/code",),allowed_hosts=("example.com",),
                max_depth=1,max_requests=4,max_documents=2,
                max_response_bytes=65536,max_total_bytes=131072,
            ),
            scope={"tenant_id":"tenant","owner_id":"owner"},
            consent={"consent_id":"code-structure-rights",
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

    def test_python_and_typescript_annotated_through_real_worker(self):
        for mime,body,expected in (
            ("text/x-python",PYTHON,"FlightEngine.simulate"),
            ("text/x-typescript",JS,"DragonBuilder"),
            ("text/x-rust",RUST,"construct_world"),
            ("text/x-go",GO,"RenderWorld"),
        ):
            with self.subTest(mime=mime):
                run,fetcher=self.capture(mime,body)
                state=run.snapshot()
                self.assertEqual(state["usage"]["requests"],2)
                self.assertEqual(state["usage"]["documents"],1)
                self.assertEqual(len(fetcher.calls),2)
                self.assertIn(expected,run.sources()[0]["text"])
                self.assertEqual(run.sources()[0]["review_state"],"unreviewed")
                self.assertFalse(run.sources()[0]["provenance"]["training_permission"])
                self.assertEqual(
                    CrawlRun.from_snapshot(state,fetcher=fetcher).snapshot(),
                    state,
                )

    def test_invalid_python_keeps_untrusted_text_not_false_ast(self):
        run,fetcher=self.capture("text/x-python","def broken(\n bad")
        self.assertEqual(run.snapshot()["usage"]["documents"],1)
        self.assertNotIn("python_ast",run.sources()[0]["text"])
        self.assertEqual(len(fetcher.calls),2)

    def test_declared_imports_cannot_add_network_requests(self):
        run,fetcher=self.capture(
            "text/x-python","import http\nfrom secrets import token_hex\n"
            "def safe(): return 1\n",
        )
        self.assertEqual(len(fetcher.calls),2)
        self.assertEqual(run.snapshot()["frontier"],[])


if __name__=="__main__":
    unittest.main()
