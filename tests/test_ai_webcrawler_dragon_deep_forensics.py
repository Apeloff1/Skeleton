"""Second-wave Dragon Atlas forensics: metadata-only hostile evidence checks."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest

import test_ai_webcrawler_dragon_atlas as fixtures
from skeleton.ai.webcrawler.dragon_campaign_stack.forensics import (
    compose_atlas_forensics, verify_atlas_forensics, bind_selected_frames,
    inspect_sentence_echoes, inspect_active_content, inspect_privacy_signals,
    measure_host_exposure, inspect_polarity_candidates,
)


class DeepForensicTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DragonAtlasRegression(
            methodName="test_empty_atlas_review_only_and_trace_valid",
        )
        self.f.setUp()
        self.now = self.f.now + 3
        text = fixtures.research_text("deep")
        self.single = self.f.with_sources(("https://example.com/a", text))
        self.duo = self.f.with_sources(
            ("https://example.com/a", text),
            ("https://example.org/b", text),
        )

    def frames(self, snapshot=None):
        current = self.single if snapshot is None else snapshot
        atlas = self.f.atlas(current)
        rows = bind_selected_frames(
            self.f.mandate, current, atlas.policies, atlas.retrieval,
            now=self.now, authorized=True,
        )
        return atlas, rows

    def test_twenty_stage_trace_replays_without_page_body(self):
        atlas, _ = self.frames(self.single)
        report = compose_atlas_forensics(
            self.f.mandate, self.single, atlas, now=self.now, authorized=True,
        )
        self.assertEqual(len(report.stages), 26)
        self.assertEqual(report.stages[-1].name, "review_only_forensic_queue")
        self.assertFalse(report.web_or_model_invoked)
        self.assertFalse(report.source_text_exported)
        verify_atlas_forensics(
            self.f.mandate, self.single, atlas, report,
            now=self.now, authorized=True,
        )

    def test_sentence_echoes_are_hashes_not_quotes(self):
        _, frames = self.frames(self.duo)
        report = inspect_sentence_echoes(frames)
        self.assertFalse(report.literal_sentences_exported)
        self.assertFalse(report.copying_confirmed)
        self.assertFalse(report.sources_independent)
        for row in report.echoes:
            self.assertEqual(len(row.normalized_sentence_hash), 64)
            self.assertGreaterEqual(len(row.source_ids), 2)

    def test_source_echo_capacity_is_fail_closed(self):
        _, frames = self.frames(self.single)
        with self.assertRaises(ValueError):
            inspect_sentence_echoes(frames, max_sentences=0)
        with self.assertRaises(ValueError):
            inspect_sentence_echoes(frames, min_sentence_chars=4)

    def test_active_content_signals_do_not_render_urls(self):
        _, frames = self.frames()
        self.assertTrue(frames.frames)
        hostile = "<script>alert(1)</script><iframe src='javascript:alert(1)'></iframe>"
        edited = replace(frames, frames=(
            replace(frames.frames[0], text=hostile),
        ))
        report = inspect_active_content(edited)
        codes = {code for row in report.findings for code in row.rule_codes}
        self.assertIn("html_script", codes)
        self.assertIn("html_iframe", codes)
        self.assertIn("javascript_scheme", codes)
        self.assertFalse(report.browser_rendering_performed)
        self.assertFalse(report.external_urls_opened)
        self.assertNotIn(hostile, json.dumps(asdict(report)))

    def test_privacy_rules_exclude_sensitive_matches(self):
        _, frames = self.frames()
        value = "person@example.com"
        hostile = "secret_key=" + ("z" * 25) + " " + value
        edited = replace(frames, frames=(
            replace(frames.frames[0], text=hostile),
        ))
        report = inspect_privacy_signals(edited)
        codes = {code for row in report.findings for code in row.rule_codes}
        self.assertIn("email_address", codes)
        self.assertIn("possible_api_credential", codes)
        self.assertFalse(report.captured_values_exported)
        self.assertFalse(report.credential_network_test_performed)
        self.assertNotIn(value, json.dumps(asdict(report)))
        self.assertNotIn('z' * 25, json.dumps(asdict(report)))

    def test_host_exposure_is_diagnostic_not_independence(self):
        atlas, frames = self.frames(self.duo)
        exposure = measure_host_exposure(frames, atlas.workbench.objectives)
        self.assertEqual(len(exposure.by_objective), 1)
        row = exposure.by_objective[0]
        self.assertGreaterEqual(row.passage_hhi, 0)
        self.assertLessEqual(row.passage_hhi, 1)
        self.assertLessEqual(row.effective_host_count, max(1, row.distinct_hosts))
        self.assertFalse(exposure.independent_sources_verified)

    def test_negative_statement_review_is_not_truth_conclusion(self):
        _, frames = self.frames(self.duo)
        sources = {f.anchor.source_id: f for f in frames.frames}
        self.assertGreaterEqual(len(sources), 2)
        rows = list(sources.values())[:2]
        left = "Archive capture methodology confirms stable audit records."
        right = "Archive capture methodology does not confirm stable audit records."
        modified = replace(frames, frames=(
            replace(rows[0], text=left),
            replace(rows[1], text=right),
        ))
        report = inspect_polarity_candidates(modified, min_shared_terms=4)
        self.assertTrue(report.leads)
        self.assertFalse(report.truth_assessed)
        self.assertFalse(report.source_text_exported)
        self.assertFalse(report.leads[0].factual_contradiction_proven)
        self.assertNotIn(left, json.dumps(asdict(report)))

    def test_rejected_foreign_objective_does_not_enter_host_exposure(self):
        atlas, frames = self.frames(self.single)
        altered = replace(frames, frames=(replace(
            frames.frames[0], anchor=replace(
                frames.frames[0].anchor, objective_ids=("foreign-claim",),
            ),
        ),))
        with self.assertRaises(PermissionError):
            measure_host_exposure(altered, atlas.workbench.objectives)

    def test_review_queue_surfaces_deep_risk_without_text(self):
        atlas, _ = self.frames(self.duo)
        report = compose_atlas_forensics(
            self.f.mandate, self.duo, atlas, now=self.now, authorized=True,
        )
        self.assertFalse(report.reviews.automatic_publication_permitted)
        self.assertTrue(all(not x.model_may_decide for x in report.reviews.tasks))
        self.assertTrue(all(len(x.task_id) == 24 for x in report.reviews.tasks))


if __name__ == "__main__":
    unittest.main()
