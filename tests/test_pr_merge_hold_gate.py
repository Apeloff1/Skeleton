"""Adversarial regression for trusted-base, live-metadata PR merge hold checks."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.check_pr_merge_hold import (
    MAX_API_BYTES,
    MergeHoldGateError,
    _decode_json,
    fetch_current_pr,
    validate_current_pr,
)

REPOSITORY = "Apeloff1/Skeleton"
HEAD = "a" * 40
BASE = "b" * 40


def pr(*, title="fix: qualified tests", body="No release approval implied.", number=123):
    return {
        "number": number,
        "state": "open",
        "title": title,
        "body": body,
        "labels": [],
        "head": {"sha": HEAD},
        "base": {"ref": "main", "sha": BASE, "repo": {"full_name": REPOSITORY}},
    }


def event(pr_data=None):
    candidate = pr_data if pr_data is not None else pr()
    return {
        "number": candidate["number"],
        "repository": {"full_name": REPOSITORY},
        "pull_request": copy.deepcopy(candidate),
    }


class PRMergeHoldGateTests(unittest.TestCase):
    def test_ordinary_current_pr_is_not_falsely_held(self):
        candidate = pr()
        validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_explicit_hold_in_title_blocks_even_with_ordinary_body(self):
        candidate = pr(title="REVIEW ONLY — DO NOT MERGE")
        with self.assertRaisesRegex(MergeHoldGateError, "explicit PR"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_explicit_hold_in_body_blocks(self):
        candidate = pr(body="Do not auto-merge until security and device gates pass")
        with self.assertRaisesRegex(MergeHoldGateError, "explicit PR"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_unicode_confusable_spacing_blocks(self):
        candidate = pr(body="ＤＯ　ＮＯＴ　ＭＥＲＧＥ")
        with self.assertRaisesRegex(MergeHoldGateError, "explicit PR"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_invisible_format_control_blocks(self):
        candidate = pr(body="Do\u200bnot merge")
        with self.assertRaisesRegex(MergeHoldGateError, "explicit PR"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_live_hold_added_after_event_fails_stale_authority(self):
        candidate = pr()
        live = pr(body="DO NOT MERGE")
        with self.assertRaisesRegex(MergeHoldGateError, "changed since workflow event"):
            validate_current_pr(event(candidate), live, REPOSITORY)

    def test_live_hold_removed_after_event_requires_new_check(self):
        candidate = pr(body="DO NOT MERGE")
        with self.assertRaisesRegex(MergeHoldGateError, "changed since workflow event"):
            validate_current_pr(event(candidate), pr(), REPOSITORY)

    def test_do_not_merge_label_is_hard_block_even_without_body_hold(self):
        candidate = pr(body="Ordinary release notes.")
        candidate["labels"] = [{"name": "do-not-merge", "id": 123}]
        with self.assertRaisesRegex(MergeHoldGateError, "label merge hold"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_automerge_off_label_is_hard_block(self):
        candidate = pr()
        candidate["labels"] = [{"name": "automerge:off"}]
        with self.assertRaisesRegex(MergeHoldGateError, "label merge hold"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_unicode_label_confusable_cannot_bypass_hold(self):
        candidate = pr()
        candidate["labels"] = [{"name": "ＤＯ－ＮＯＴ－ＭＥＲＧＥ"}]
        with self.assertRaisesRegex(MergeHoldGateError, "label merge hold"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_label_added_after_event_invalidates_old_check(self):
        candidate = pr()
        live = copy.deepcopy(candidate)
        live["labels"] = [{"name": "do-not-merge"}]
        with self.assertRaisesRegex(MergeHoldGateError, "changed since workflow"):
            validate_current_pr(event(candidate), live, REPOSITORY)

    def test_hold_label_removed_requires_fresh_event_and_check(self):
        candidate = pr()
        candidate["labels"] = [{"name": "do-not-merge"}]
        live = pr()
        with self.assertRaisesRegex(MergeHoldGateError, "changed since workflow"):
            validate_current_pr(event(candidate), live, REPOSITORY)

    def test_absent_or_malformed_live_labels_fail_closed(self):
        for labels in (
            None, "do-not-merge", [None], [{"name": None}],
            [{"name": chr(10)}],
        ):
            candidate = pr()
            if labels is None:
                del candidate["labels"]
            else:
                candidate["labels"] = labels
            with self.subTest(labels=labels), self.assertRaises(MergeHoldGateError):
                validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_ordinary_nonhold_labels_are_allowed(self):
        candidate = pr()
        candidate["labels"] = [{"name": "security-review-complete"}, {"name": "docs"}]
        validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_changed_head_invalidates_old_success(self):
        candidate = pr()
        live = pr()
        live["head"]["sha"] = "c" * 40
        with self.assertRaisesRegex(MergeHoldGateError, "changed since workflow event"):
            validate_current_pr(event(candidate), live, REPOSITORY)

    def test_changed_base_invalidates_old_success(self):
        candidate = pr()
        live = pr()
        live["base"]["sha"] = "c" * 40
        with self.assertRaisesRegex(MergeHoldGateError, "changed since workflow event"):
            validate_current_pr(event(candidate), live, REPOSITORY)

    def test_different_target_branch_is_rejected(self):
        candidate = pr()
        candidate["base"]["ref"] = "unsafe"
        with self.assertRaisesRegex(MergeHoldGateError, "unexpected PR base"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_different_repository_is_rejected(self):
        candidate = pr()
        candidate["base"]["repo"]["full_name"] = "attacker/Skeleton"
        with self.assertRaisesRegex(MergeHoldGateError, "unexpected PR base"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_noninteger_pr_number_rejected(self):
        candidate = pr()
        data = event(candidate)
        data["number"] = True
        with self.assertRaisesRegex(MergeHoldGateError, "invalid event PR"):
            validate_current_pr(data, candidate, REPOSITORY)

    def test_invalid_title_type_rejected(self):
        candidate = pr()
        candidate["title"] = ["DO NOT MERGE"]
        with self.assertRaisesRegex(MergeHoldGateError, "title must be text"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_closed_pr_rejected(self):
        candidate = pr()
        candidate["state"] = "closed"
        with self.assertRaisesRegex(MergeHoldGateError, "not open"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_unbounded_text_is_rejected(self):
        candidate = pr(body="x" * 131073)
        with self.assertRaisesRegex(MergeHoldGateError, "explicit PR"):
            validate_current_pr(event(candidate), candidate, REPOSITORY)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(MergeHoldGateError, "duplicate JSON"):
            _decode_json(b'{"number":1,"number":2}', maximum=100)

    def test_oversized_api_json_rejected_before_parsing(self):
        with self.assertRaisesRegex(MergeHoldGateError, "bounded size"):
            _decode_json(b" " * (MAX_API_BYTES + 1), maximum=MAX_API_BYTES)

    def test_malformed_utf8_rejected(self):
        with self.assertRaisesRegex(MergeHoldGateError, "malformed JSON"):
            _decode_json(b"\xff", maximum=100)

    def test_live_api_request_is_bounded_and_authenticated(self):
        candidate = pr()
        raw = json.dumps(candidate).encode("utf-8")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, size):
                self_size = size
                assert self_size == MAX_API_BYTES + 1
                return raw

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 15)
            self.assertEqual(request.full_url, "https://api.github.com/repos/Apeloff1/Skeleton/pulls/123")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
            return Response()

        with patch("scripts.check_pr_merge_hold.urlopen", side_effect=fake_urlopen):
            self.assertEqual(fetch_current_pr(REPOSITORY, 123, "test-token"), candidate)

    def test_missing_token_fails_closed(self):
        with self.assertRaisesRegex(MergeHoldGateError, "missing read-only"):
            fetch_current_pr(REPOSITORY, 123, "")

    def test_workflows_separate_privileged_gate_from_source_tests(self):
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        gate = (root / "pr-merge-hold.yml").read_text(encoding="utf-8")
        qualification = (root / "pr-merge-hold-qualification.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", gate)
        self.assertNotIn("  pull_request:", gate)
        self.assertNotIn("if: github.event_name", gate)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", gate)
        self.assertIn("persist-credentials: false", gate)
        self.assertIn("pull-requests: read", gate)
        self.assertIn("contents: read", gate)
        self.assertNotIn("pull-requests: write", gate)
        self.assertNotIn("contents: write", gate)
        self.assertNotIn("github.event.pull_request.head.sha", gate)
        self.assertIn("edited", gate)
        self.assertIn("synchronize", gate)
        self.assertIn("name: PR Merge Hold Gate", gate)

        self.assertIn("  pull_request:", qualification)
        self.assertNotIn("pull_request_target:", qualification)
        self.assertIn("github.event.pull_request.head.sha", qualification)
        self.assertIn("persist-credentials: false", qualification)
        self.assertIn("contents: read", qualification)
        self.assertNotIn("contents: write", qualification)
        self.assertNotIn("pull-requests: write", qualification)
        self.assertIn("name: PR Merge Hold Qualification", qualification)


if __name__ == "__main__":
    unittest.main()
