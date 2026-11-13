"""Integrity checks for the complete 151-CodeQL-alert lineage inventory."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/security/codeql-open-151-lineage-2026-11-11.json"

EXPECTED_RULE_COUNTS = {
    "py/stack-trace-exposure": 125,
    "py/path-injection": 9,
    "py/polynomial-redos": 5,
    "js/insecure-randomness": 4,
    "py/full-ssrf": 2,
    "py/incomplete-url-substring-sanitization": 2,
    "py/reflective-xss": 1,
    "py/clear-text-storage-sensitive-data": 1,
    "js/incomplete-sanitization": 1,
    "js/incomplete-multi-character-sanitization": 1,
}


def test_snapshot_tracks_every_alert_with_unique_stable_id():
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    assert payload["schema"] == "codeql-alert-lineage/v1"
    assert payload["source_issue"] == 1016
    findings = payload["findings"]
    assert len(findings) == payload["observed_code_scanning_alerts"] == 151
    ids = [item["number"] for item in findings]
    assert len(set(ids)) == 151
    assert ids == sorted(ids)


def test_rules_paths_and_urls_are_grounded_not_guessed():
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    findings = payload["findings"]
    assert dict(Counter(item["rule_id"] for item in findings)) == EXPECTED_RULE_COUNTS
    assert payload["rule_counts"] == EXPECTED_RULE_COUNTS
    assert len({item["path"] for item in findings}) == 65
    for item in findings:
        assert item["state_at_inventory"] == "open"
        assert item["resolution"] == "requires-current-main-codeql-reanalysis"
        assert item["severity"] in {"critical", "high", "medium", "low", "warning", "error", "note"}
        assert item["line"] >= 1
        assert item["path"] and not item["path"].startswith("/")
        assert ".." not in Path(item["path"]).parts
        link = urlsplit(item["url"])
        assert link.scheme == "https"
        assert link.netloc == "github.com"
        assert f"/security/code-scanning/{item['number']}" in link.path


def test_inventory_cannot_misrepresent_code_review_as_closed_alerts():
    data = LEDGER.read_text(encoding="utf-8")
    payload = json.loads(data)
    assert "do-not-merge" in payload["security_hold"]
    assert "closure evidence" in payload["scope"]
    for item in payload["findings"]:
        assert not any(
            key in item for key in ("fixed", "dismissed", "closed_at", "resolved_at", "merged")
        )
