"""Browser fork reconciliation is CSP-bound and remains noncommitting."""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_story_html import (
    _JS, render_story_html,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def test_browser_merge_has_explicit_noncommitting_editor_and_csp():
    html = render_story_html(read_blueprint(PROJECT)).decode("utf-8")
    for identifier in (
        "checkpoint-ancestor", "checkpoint-merge", "checkpoint-merge-status",
        "checkpoint", "checkpoint-restore",
    ):
        assert ("id='" + identifier + "'") in html
    assert "function mergeCheckpoint()" in _JS
    assert "parseCheckpoint(proposed)" in _JS
    assert "chosen.splice" not in _JS.split("function mergeCheckpoint(){", 1)[1].split(
        "function render(){", 1)[0]
    assert "checkpoint.value=proposed;" in _JS
    assert "no external evidence is verified" in _JS
    digest = b64encode(sha256(_JS.encode("utf-8")).digest()).decode("ascii")
    assert "'sha256-" + digest + "'" in html
    assert "default-src 'none'" in html
    assert "object-src 'none'" in html
    assert "<script>" + _JS + "</script>" in html


def test_browser_fork_editor_does_not_use_network_or_eval():
    body = _JS.split("function mergeCheckpoint(){", 1)[1].split(
        "function render(){", 1)[0]
    for forbidden in ("fetch(", "XMLHttpRequest", "eval(", "new Function(",
                      "innerHTML", "localStorage", "window.open("):
        assert forbidden not in body
    assert "subsequence(current)" in body
    assert "subsequence(candidate)" in body
    assert "prefix(ancestor,current)" in body
    assert "prefix(ancestor,candidate)" in body
