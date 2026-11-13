"""Durable Jeeves organization, model isolation and portable backup acceptance.

These checks exercise the SQLite authority and real authenticated loopback HTTP.
Organization never becomes conversation context or inference execution evidence.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore, _stable_bytes
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError


MODEL = "a" * 64
TOKENIZER = "b" * 64


class ConversationOrganizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / "conversations.sqlite3"
        self.store = OfflineChatStore(self.database)
        self.addCleanup(lambda: self.store.close())

    def create(self, prompt: str | None = None) -> str:
        sid = self.store.create(MODEL, TOKENIZER)
        if prompt:
            prior = self.store.load(sid, MODEL, TOKENIZER)
            self.store.commit(
                session=prior, request_id="request_1", request_digest="c" * 64,
                transcript=prior.transcript.append("user", prompt).append("assistant", "Saved answer"),
                text="Saved answer", output_digest=sha256(b"Saved answer").hexdigest(),
                prompt_tokens=4, generated_tokens=2,
            )
        return sid

    def metadata(self, sid):
        return self.store.session_metadata(sid, MODEL, TOKENIZER)

    def update(self, sid, changes, **kwargs):
        return self.store.update_metadata(sid, MODEL, TOKENIZER, changes, **kwargs)

    def test_reopen_preserves_organization_without_modifying_history_or_receipts(self):
        sid = self.create("Original question")
        before = self.store.load(sid, MODEL, TOKENIZER)
        receipt = self.store.replay(sid, "request_1", "c" * 64)
        changed = self.update(sid, {"title": "  実験 🌱  ", "pinned": True, "archived": True},
                              expected_metadata_revision=0)
        self.assertEqual(changed["title"], "実験 🌱")
        self.assertEqual(changed["metadata_revision"], 1)
        self.assertEqual(self.store.load(sid, MODEL, TOKENIZER), before)
        self.assertEqual(self.store.replay(sid, "request_1", "c" * 64), receipt)
        with OfflineChatStore(self.database) as peer:
            self.assertEqual(peer.session_metadata(sid, MODEL, TOKENIZER), changed)
            self.assertEqual(peer.load(sid, MODEL, TOKENIZER), before)

    def test_auto_title_reset_and_identical_updates_are_idempotent(self):
        sid = self.create("First useful question")
        self.assertEqual(self.metadata(sid)["title"], "First useful question")
        self.update(sid, {"title": "My topic"})
        self.assertEqual(self.metadata(sid)["custom_title"], "My topic")
        result = self.update(sid, {"title": ""}, expected_metadata_revision=1)
        self.assertEqual(result["title"], "First useful question")
        self.assertEqual(result["custom_title"], "")
        self.assertEqual(result["metadata_revision"], 2)
        again = self.update(sid, {"title": "", "pinned": False}, expected_metadata_revision=2)
        self.assertEqual(result, again)

    def test_metadata_cas_is_independent_of_turn_revision_and_other_connections(self):
        sid = self.create("Already revision one")
        with OfflineChatStore(self.database) as peer:
            peer.update_metadata(sid, MODEL, TOKENIZER, {"title": "Peer title"},
                                 expected_metadata_revision=0)
            with self.assertRaisesRegex(RuntimeContractError, "revision conflict"):
                self.update(sid, {"pinned": True}, expected_metadata_revision=0)
        self.assertFalse(self.metadata(sid)["pinned"])
        self.assertEqual(self.store.load(sid, MODEL, TOKENIZER).revision, 1)

    def test_concurrent_stores_accept_only_one_exact_revision_update(self):
        sid = self.create()
        gate = threading.Barrier(2)
        def update_from_peer(title):
            with OfflineChatStore(self.database) as peer:
                gate.wait(timeout=5)
                try:
                    return peer.update_metadata(sid, MODEL, TOKENIZER, {"title": title},
                                                expected_metadata_revision=0)
                except RuntimeContractError as error:
                    return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update_from_peer, ("One", "Two")))
        self.assertEqual(sum(isinstance(item, dict) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, str) and "revision conflict" in item
                             for item in outcomes), 1)
        self.assertEqual(self.metadata(sid)["metadata_revision"], 1)

    def test_model_and_tokenizer_scope_blocks_reads_writes_and_search(self):
        sid = self.create()
        self.update(sid, {"title": "Private title"})
        for model, tokenizer in [("d" * 64, TOKENIZER), (MODEL, "d" * 64)]:
            with self.subTest(model=model, tokenizer=tokenizer):
                with self.assertRaises(RuntimeContractError):
                    self.store.session_metadata(sid, model, tokenizer)
                with self.assertRaises(RuntimeContractError):
                    self.store.update_metadata(sid, model, tokenizer, {"title": "Other"})
                self.assertEqual(self.store.session_summaries(model, tokenizer)["sessions"], [])
        self.assertEqual(self.metadata(sid)["title"], "Private title")

    def test_active_archive_search_title_and_literal_wildcard_behavior(self):
        visible = self.create("ordinary prompt")
        archived = self.create("hidden body")
        self.update(visible, {"title": "Release 100%_ready"})
        self.update(archived, {"title": "Archived topic", "archived": True})
        self.assertEqual([x["session_id"] for x in self.store.session_summaries(
            MODEL, TOKENIZER, query="100%_")["sessions"]], [visible])
        self.assertEqual(self.store.session_summaries(MODEL, TOKENIZER, query="Archived")["sessions"], [])
        self.assertEqual([x["session_id"] for x in self.store.session_summaries(
            MODEL, TOKENIZER, query="hidden", archived=True)["sessions"]], [archived])
        self.update(archived, {"archived": False})
        self.assertEqual(self.store.session_summaries(MODEL, TOKENIZER, archived=True)["sessions"], [])

    def test_pinned_pagination_crosses_groups_without_duplicates_or_omissions(self):
        ids = [self.create() for _ in range(7)]
        self.update(ids[1], {"pinned": True})
        self.update(ids[3], {"pinned": True})
        expected = [ids[3], ids[1], *reversed([sid for sid in ids if sid not in {ids[1], ids[3]}])]
        found, cursor = [], None
        for _ in range(8):
            page = self.store.session_summaries(MODEL, TOKENIZER, limit=2, cursor=cursor)
            found.extend(x["session_id"] for x in page["sessions"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(found, expected)
        self.assertEqual(len(found), len(set(found)))

    def test_title_and_history_search_use_unicode_casefold_and_canonical_equivalence(self):
        nordic = self.create("Ordinary question")
        german = self.create("Visit the Straße for the answer")
        accent = self.create()
        self.update(nordic, {"title": "ÅNGSTRÖM research"})
        self.update(accent, {"title": "Café notes"})
        for query, expected in [("ångström", nordic), ("STRASSE", german),
                                ("Cafe\u0301", accent)]:
            with self.subTest(query=query):
                page = self.store.session_summaries(MODEL, TOKENIZER, query=query)
                self.assertEqual([item["session_id"] for item in page["sessions"]], [expected])

    def test_rejects_hostile_metadata_without_any_partial_write(self):
        sid = self.create()
        bad = [
            {}, {"unknown": True}, {"title": None}, {"title": 3},
            {"title": "a" * 101}, {"title": "bad\x00title"},
            {"title": "two\nlines"}, {"title": "\ud800"},
            {"pinned": 1}, {"archived": "false"},
            {"title": "Would change", "archived": 0},
        ]
        before = self.metadata(sid)
        for fields in bad:
            with self.subTest(fields=repr(fields)):
                with self.assertRaises(RuntimeContractError):
                    self.update(sid, fields)
                self.assertEqual(self.metadata(sid), before)
        for revision in [-1, True, "0", 2**63]:
            with self.assertRaises(RuntimeContractError):
                self.update(sid, {"title": "Safe"}, expected_metadata_revision=revision)

    def test_invalid_filters_and_cursors_are_rejected(self):
        for kwargs in [{"archived": 0}, {"query": "\ud800"}, {"query": "x" * 257},
                       {"cursor": "2:123:valid"}, {"cursor": "1:99999999999999999999:s"},
                       {"cursor": "1:1:../escape"}, {"limit": True}]:
            with self.subTest(kwargs=repr(kwargs)):
                with self.assertRaises(RuntimeContractError):
                    self.store.session_summaries(MODEL, TOKENIZER, **kwargs)

    def test_legacy_cursor_still_continues_unpinned_group(self):
        self.create()
        self.create()
        page = self.store.session_summaries(MODEL, TOKENIZER, limit=1)
        legacy = page["next_cursor"].split(":", 1)[1]
        next_page = self.store.session_summaries(MODEL, TOKENIZER, cursor=legacy)
        self.assertEqual(len(next_page["sessions"]), 1)
        self.assertNotEqual(page["sessions"][0]["session_id"], next_page["sessions"][0]["session_id"])

    def test_fork_copies_title_but_starts_active_unpinned_with_independent_clock(self):
        sid = self.create("Original history")
        self.update(sid, {"title": "My research", "pinned": True, "archived": True})
        fork = self.store.fork(sid, MODEL, TOKENIZER)
        copied = self.metadata(fork)
        self.assertEqual(copied["title"], "My research")
        self.assertFalse(copied["pinned"])
        self.assertFalse(copied["archived"])
        self.update(fork, {"title": "Separate branch"}, expected_metadata_revision=1)
        self.assertEqual(self.metadata(sid)["title"], "My research")
        self.assertTrue(self.metadata(sid)["archived"])

    def test_legacy_bundle_stays_compatible_and_v3_roundtrip_restores_organization(self):
        sid = self.create("Portable history")
        legacy = self.store.export_bundle(sid, MODEL, TOKENIZER)
        self.assertEqual(json.loads(legacy)["body"]["schema"], "skeleton.ai.offline-chat-bundle.v1")
        self.update(sid, {"title": "Portable 🌍", "pinned": True, "archived": True})
        exported = self.store.export_bundle(sid, MODEL, TOKENIZER)
        body = json.loads(exported)["body"]
        self.assertEqual(body["schema"], "skeleton.ai.offline-chat-bundle.v3")
        restored = self.store.import_bundle(exported, MODEL, TOKENIZER)
        self.assertNotEqual(restored, sid)
        metadata = self.metadata(restored)
        self.assertEqual(metadata["title"], "Portable 🌍")
        self.assertTrue(metadata["pinned"] and metadata["archived"])
        self.assertEqual(metadata["metadata_revision"], 1)
        self.assertEqual(self.store.load(restored, MODEL, TOKENIZER).transcript,
                         self.store.load(sid, MODEL, TOKENIZER).transcript)
        restored_legacy = self.store.import_bundle(legacy, MODEL, TOKENIZER)
        self.assertEqual(self.metadata(restored_legacy)["custom_title"], "")
        self.assertFalse(self.metadata(restored_legacy)["archived"])

    def test_tampered_or_malformed_v3_metadata_never_creates_session(self):
        sid = self.create()
        self.update(sid, {"title": "Export me"})
        original = json.loads(self.store.export_bundle(sid, MODEL, TOKENIZER))
        count_before = len(self.store.list_sessions(MODEL, TOKENIZER))
        for value in [{"title": "a" * 101, "pinned": False, "archived": False},
                      {"title": "Fine", "pinned": 1, "archived": False},
                      {"title": "Fine", "pinned": False, "archived": False, "extra": True}]:
            envelope = json.loads(json.dumps(original))
            envelope["body"]["metadata"] = value
            envelope["sha256"] = sha256(_stable_bytes(envelope["body"])).hexdigest()
            with self.assertRaises(RuntimeContractError):
                self.store.import_bundle(_stable_bytes(envelope), MODEL, TOKENIZER)
        original["body"]["metadata"]["title"] = "Tampered without digest update"
        with self.assertRaisesRegex(RuntimeContractError, "digest mismatch"):
            self.store.import_bundle(_stable_bytes(original), MODEL, TOKENIZER)
        self.assertEqual(len(self.store.list_sessions(MODEL, TOKENIZER)), count_before)

    def test_v3_organization_backup_retains_exact_grounded_passage_receipts(self):
        from skeleton.app.offline_grounding import prepare_evidence
        from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
        library = OfflineKnowledgeLibrary(self.store, MODEL, TOKENIZER)
        library.add_text("Reference", "The copper relay station opens at seven.")
        question = "When does the copper relay station open?"
        manifest = prepare_evidence(question, "c" * 64, library.search(question), MODEL, TOKENIZER)
        sid = self.create()
        prior = self.store.load(sid, MODEL, TOKENIZER)
        self.store.commit(
            session=prior, request_id="grounded_request", request_digest="c" * 64,
            transcript=prior.transcript.append("user", question).append("assistant", "At seven."),
            text="At seven.", output_digest=sha256(b"At seven.").hexdigest(),
            prompt_tokens=40, generated_tokens=3, evidence_manifest=manifest,
        )
        v2 = self.store.export_bundle(sid, MODEL, TOKENIZER)
        self.assertEqual(json.loads(v2)["body"]["schema"], "skeleton.ai.offline-chat-bundle.v2")
        v2_copy = self.store.import_bundle(v2, MODEL, TOKENIZER)
        self.update(sid, {"title": "Cited relay answer", "pinned": True})
        v3 = self.store.export_bundle(sid, MODEL, TOKENIZER)
        v3_copy = self.store.import_bundle(v3, MODEL, TOKENIZER)
        original = self.store.turn_evidence(sid, MODEL, TOKENIZER)
        self.assertEqual(self.store.turn_evidence(v2_copy, MODEL, TOKENIZER), original)
        self.assertEqual(self.store.turn_evidence(v3_copy, MODEL, TOKENIZER), original)
        self.assertEqual(self.metadata(v3_copy)["title"], "Cited relay answer")

    def test_delete_cascades_organization_and_existing_database_migrates(self):
        sid = self.create()
        self.update(sid, {"title": "Erase this label"})
        self.store.delete(sid, MODEL, TOKENIZER)
        self.assertEqual(self.store._db.execute("SELECT COUNT(*) FROM offline_session_metadata").fetchone(), (0,))
        old = self.create("Legacy session")
        self.store._db.execute("DROP TABLE offline_session_metadata")
        self.store.close()
        self.store = OfflineChatStore(self.database)
        self.assertEqual(self.metadata(old)["title"], "Legacy session")
        self.assertEqual(self.metadata(old)["metadata_revision"], 0)
        self.update(old, {"pinned": True}, expected_metadata_revision=0)
        self.assertTrue(self.metadata(old)["pinned"])


class OrganizationHTTPTests(unittest.TestCase):
    def setUp(self):
        from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
        from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
        from skeleton.app.offline_http import LocalOnlyHTTPServer, OfflineHTTPApplication
        from skeleton.cortex.transformer import TinyTransformer
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        model = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
            vocab=("system:", "user:", "assistant:", "hello", "world"),
            dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
        )))
        self.application = OfflineHTTPApplication(model, Path(self.directory.name) / "http.sqlite3",
                                                  token="t" * 64)
        self.server = LocalOnlyHTTPServer(self.application)
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        self.application.close()

    def request(self, method, path, body=None, *, authorized=True):
        headers = {"Authorization": "Bearer " + "t" * 64} if authorized else {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_authenticated_metadata_cas_search_archive_and_get_complete_journey(self):
        status, created = self.request("POST", "/v1/sessions", {})
        self.assertEqual(status, 201)
        path = "/v1/sessions/" + created["session_id"]
        status, _ = self.request("POST", path + "/metadata", {"title": "No authority"}, authorized=False)
        self.assertEqual(status, 401)
        status, updated = self.request("POST", path + "/metadata",
                                       {"title": "Project notes", "pinned": True, "expected_metadata_revision": 0})
        self.assertEqual(status, 200)
        self.assertEqual(updated["metadata_revision"], 1)
        status, loaded = self.request("GET", path)
        self.assertEqual(status, 200)
        self.assertEqual(loaded["title"], "Project notes")
        self.assertTrue(loaded["pinned"])
        self.assertEqual(loaded["revision"], 0)
        status, conflict = self.request("POST", path + "/metadata",
                                        {"archived": True, "expected_metadata_revision": 0})
        self.assertEqual(status, 409)
        self.assertEqual(conflict["error"], "local conversation conflict")
        self.request("POST", path + "/metadata", {"archived": True, "expected_metadata_revision": 1})
        _, active = self.request("POST", "/v1/sessions/search", {"query": "Project"})
        _, archive = self.request("POST", "/v1/sessions/search", {"query": "Project", "archived": True})
        self.assertEqual(active["sessions"], [])
        self.assertEqual(archive["sessions"][0]["session_id"], created["session_id"])
        self.assertTrue(archive["sessions"][0]["archived"])

    def test_bad_http_metadata_is_rejected_with_safe_errors_and_no_change(self):
        _, created = self.request("POST", "/v1/sessions", {})
        path = "/v1/sessions/" + created["session_id"]
        for body in [{}, {"title": "x" * 101}, {"archived": 1},
                     {"expected_metadata_revision": None, "pinned": True},
                     {"expected_metadata_revision": True, "title": "No"},
                     {"title": "Valid", "extra": "not permitted"}]:
            with self.subTest(body=body):
                status, payload = self.request("POST", path + "/metadata", body)
                self.assertEqual(status, 400)
                self.assertIn("error", payload)
        _, loaded = self.request("GET", path)
        self.assertEqual(loaded["metadata_revision"], 0)


if __name__ == "__main__":
    unittest.main()
