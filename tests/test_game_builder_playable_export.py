"""Full offline HTML game output, CLI execution and deterministic replay tests."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.playable_cli import main
from skeleton.ai.game_builder.playable_compiler import (
    CompiledPlayableProject, PlayableCompilationError,
    compile_original_game, export_compiled_project,
)
from skeleton.ai.game_builder.playable_export import (
    PlayableExportError, PlayableHTML, render_playable_world,
    write_playable_html,
)
from skeleton.ai.game_builder.playable_world import (
    GameBuildIntent, generate_playable_world,
)


def intent(**changes):
    data = {
        "project_id": "offline-quest",
        "title": "Original Cave Adventure",
        "subtitle": "Find crystals and escape with your health.",
        "seed": 11, "width": 15, "height": 11, "levels": 2,
        "collectibles_per_level": 2, "hazards_per_level": 4,
        "theme": "arcade", "starting_health": 3,
    }
    data.update(changes)
    return GameBuildIntent(**data)


class ResourceAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []
        self.scripts = []
        self.css = []
        self.meta = []

    def handle_starttag(self, tag, attrs):
        items = dict(attrs)
        for attr in ("src", "href", "action"):
            if attr in items:
                self.external.append((tag, attr, items[attr]))
        if tag == "meta" and items.get("http-equiv") == "Content-Security-Policy":
            self.meta.append(items.get("content", ""))

    def handle_data(self, data):
        pass


class HTMLGameTests(unittest.TestCase):
    def test_real_browser_game_exports_with_matching_proof(self):
        package = compile_original_game(intent(), authorized=True)
        self.assertEqual(package.proof.final_state.status, "won")
        self.assertEqual(package.playable.proof_digest, package.proof.digest)
        self.assertEqual(package.playable.world_digest, package.world.digest)
        self.assertEqual(
            package.playable.html_sha256,
            sha256(package.playable.html.encode("utf-8")).hexdigest(),
        )
        self.assertIn('<canvas id="screen"', package.playable.html)
        self.assertIn("function takeTurn(direction)", package.playable.html)
        self.assertIn("function downloadReplay()", package.playable.html)
        self.assertIn('data-action="up"', package.playable.html)
        self.assertIn('data-action="left"', package.playable.html)
        self.assertIn('data-action="down"', package.playable.html)
        self.assertIn('data-action="right"', package.playable.html)
        self.assertIn('id="text-map"', package.playable.html)
        self.assertIn("Crystal collected!", package.playable.html)
        self.assertIn("Exit locked.", package.playable.html)
        self.assertIn("Level complete!", package.playable.html)
        self.assertEqual(package.receipt()["levels"], 2)

    def test_csp_blocks_network_calls_and_third_party_content(self):
        game = compile_original_game(intent(), authorized=True)
        audit = ResourceAudit()
        audit.feed(game.playable.html)
        self.assertEqual(audit.external, [])
        self.assertEqual(len(audit.meta), 1)
        policy = audit.meta[0]
        self.assertIn("default-src 'none'", policy)
        self.assertIn("connect-src 'none'", policy)
        self.assertIn("img-src 'none'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("script-src 'sha256-", policy)
        self.assertIn("style-src 'sha256-", policy)
        self.assertNotIn("'unsafe-inline'", policy)
        self.assertNotIn("https://", game.playable.html)
        self.assertFalse(game.receipt()["network_calls"])

    def test_untrusted_title_and_subtitle_are_escaped_in_html_and_script(self):
        malicious = '</script><img src=x onerror="alert(1)">'
        compiled = compile_original_game(intent(
            title="Game " + malicious, subtitle="Research note " + malicious,
        ), authorized=True)
        html = compiled.playable.html
        self.assertNotIn(malicious, html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;/script&gt;", html)
        self.assertIn("\\u003c", html)
        audit = ResourceAudit()
        audit.feed(html)
        self.assertEqual(audit.external, [])

    def test_different_seeds_affect_game_digests(self):
        first = compile_original_game(intent(seed=11), authorized=True)
        second = compile_original_game(intent(seed=19), authorized=True)
        self.assertNotEqual(first.world.digest, second.world.digest)
        self.assertNotEqual(first.playable.html_sha256, second.playable.html_sha256)

    def test_identical_intent_yields_byte_for_byte_reproducible_export(self):
        first = compile_original_game(intent(), authorized=True)
        second = compile_original_game(intent(), authorized=True)
        self.assertEqual(first.receipt(), second.receipt())
        self.assertEqual(first.playable.html, second.playable.html)
        self.assertEqual(first.playable.html_sha256, second.playable.html_sha256)

    def test_html_renderer_refuses_nonworld_and_unauthorized_call(self):
        world = generate_playable_world(intent(), authorized=True)
        with self.assertRaises(PermissionError):
            render_playable_world(world, authorized=False)
        with self.assertRaises(PlayableExportError):
            render_playable_world({}, authorized=True)

    def test_self_contained_html_writer_is_real_file_output(self):
        compiled = compile_original_game(intent(), authorized=True)
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder) / "play.html"
            result = export_compiled_project(compiled, location, authorized=True)
            self.assertEqual(result, location)
            actual = location.read_bytes()
            self.assertEqual(sha256(actual).hexdigest(), compiled.playable.html_sha256)
            self.assertTrue(actual.startswith(b"<!doctype html>"))
            with self.assertRaises(PermissionError):
                write_playable_html(compiled.playable, location, authorized=False)

    def test_writer_rejects_modified_html_and_symlink_targets(self):
        compiled = compile_original_game(intent(), authorized=True)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "play.html"
            tampered = replace(compiled.playable, html=compiled.playable.html + "bad")
            with self.assertRaises(PlayableExportError):
                write_playable_html(tampered, destination, authorized=True)
            origin = Path(folder) / "origin.html"
            origin.write_text("do not overwrite", encoding="utf-8")
            destination.symlink_to(origin)
            with self.assertRaises(PlayableExportError):
                write_playable_html(compiled.playable, destination, authorized=True)
            self.assertEqual(origin.read_text(encoding="utf-8"), "do not overwrite")

    def test_compiler_rejects_mismatched_model_and_proof(self):
        compiled = compile_original_game(intent(), authorized=True)
        with self.assertRaises(PlayableCompilationError):
            replace(
                compiled, playable=replace(
                    compiled.playable, proof_digest="0" * 64,
                ),
            )


class PlayableCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.config = self.folder / "intent.json"
        self.output = self.folder / "game.html"
        self.replay = self.folder / "trace.json"
        self.config.write_text(json.dumps(intent().to_payload()), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args, authenticated=True):
        out, err = io.StringIO(), io.StringIO()
        argv = ["--intent", str(self.config)]
        if authenticated:
            argv.append("--trusted-local-operator")
        argv.extend(args)
        with redirect_stdout(out), redirect_stderr(err):
            result = main(argv)
        data = json.loads(out.getvalue()) if out.getvalue() else None
        return result, data, err.getvalue()

    def test_cli_build_creates_real_offline_html(self):
        code, built, error = self.invoke("build", "--output", str(self.output))
        self.assertEqual((code, error), (0, ""))
        self.assertTrue(self.output.exists())
        self.assertEqual(built["html_sha256"], sha256(self.output.read_bytes()).hexdigest())
        self.assertTrue(built["validated_gameplay_proof"])
        self.assertEqual(built["project_id"], "offline-quest")
        self.assertFalse(built["publication_authority"])

    def test_cli_can_emit_solution_and_verify_exported_browser_actions(self):
        code, solution, error = self.invoke("solve")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(solution["final_state"]["status"], "won")
        log = {
            "schema": "skeleton.game_builder.browser_actions.v1",
            "world_digest": solution["world_digest"],
            "project_id": "offline-quest",
            "actions": solution["actions"],
            "note": "Unverified client-side actions; replay via trusted Python engine.",
        }
        self.replay.write_text(json.dumps(log), encoding="utf-8")
        code, verified, error = self.invoke("verify-replay", "--input", str(self.replay))
        self.assertEqual((code, error), (0, ""))
        self.assertTrue(verified["verified"])
        self.assertFalse(verified["source_authenticity_verified"])
        self.assertEqual(verified["final_state"]["status"], "won")
        self.assertEqual(verified["replay_digest"], solution["replay_digest"])

    def test_cli_analyzes_verified_trace_into_actionable_experience(self):
        code, solution, error = self.invoke("solve")
        self.assertEqual((code, error), (0, ""))
        record = {
            "schema": "skeleton.game_builder.browser_actions.v1",
            "world_digest": solution["world_digest"],
            "project_id": "offline-quest",
            "actions": solution["actions"],
            "note": "Unverified client-side actions; replay via trusted Python engine.",
        }
        self.replay.write_text(json.dumps(record), encoding="utf-8")
        code, analysis, error = self.invoke("analyze-replay", "--input", str(self.replay))
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(analysis["schema"], "skeleton.game_builder.playability_report.v1")
        self.assertTrue(analysis["completed_game"])
        self.assertEqual(len(analysis["levels"]), 2)
        self.assertTrue(analysis["no_preference_inference"])
        self.assertTrue(analysis["requires_human_evaluation"])
        self.assertEqual(len(analysis["report_digest"]), 64)

    def test_cli_rejects_forged_world_digest(self):
        log = {
            "schema": "skeleton.game_builder.browser_actions.v1",
            "world_digest": "0" * 64,
            "project_id": "offline-quest",
            "actions": ["up"],
            "note": "fake",
        }
        self.replay.write_text(json.dumps(log), encoding="utf-8")
        code, _, error = self.invoke("verify-replay", "--input", str(self.replay))
        self.assertEqual(code, 2)
        self.assertIn("another game", error)

    def test_cli_rejects_unknown_actions_and_malformed_documents(self):
        self.replay.write_text(json.dumps({
            "schema": "skeleton.game_builder.browser_actions.v1",
            "world_digest": compile_original_game(intent(), authorized=True).world.digest,
            "project_id": "offline-quest",
            "actions": ["delete-all-files"],
            "note": "untrusted",
        }), encoding="utf-8")
        code, _, error = self.invoke("verify-replay", "--input", str(self.replay))
        self.assertEqual(code, 2)
        self.assertIn("browser action", error)
        self.config.write_text('{"seed":1,"seed":2}', encoding="utf-8")
        code, _, error = self.invoke("solve")
        self.assertEqual(code, 2)
        self.assertIn("invalid UTF-8 JSON input", error)

    def test_cli_operator_ack_is_required(self):
        code, _, error = self.invoke("solve", authenticated=False)
        self.assertEqual(code, 2)
        self.assertIn("authorization", error)

    def test_cli_refuses_nonhtml_output(self):
        code, _, error = self.invoke("build", "--output", str(self.folder / "nope.js"))
        self.assertEqual(code, 2)
        self.assertIn(".html", error)

    def test_cli_invalid_input_scope_fails_closed(self):
        bad = intent().to_payload()
        bad["seed"] = True
        self.config.write_text(json.dumps(bad), encoding="utf-8")
        code, _, error = self.invoke("solve")
        self.assertEqual(code, 2)
        self.assertIn("invalid game intent", error)

    def test_cli_is_deterministic_across_fresh_runs(self):
        first = self.invoke("solve")
        second = self.invoke("solve")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
