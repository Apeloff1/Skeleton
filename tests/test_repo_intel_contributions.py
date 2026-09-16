from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel_contributions as contributions  # noqa: E402


def test_parse_log_handles_multiline_commit_bodies(monkeypatch) -> None:
    raw = (
        "a" * 40
        + "\0Owner\0owner@example.test\0Owner\0owner@example.test\0Title\n\nBody line\nCo-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>\0\n"
        + "b" * 40
        + "\0dependabot[bot]\0support@github.com\0dependabot[bot]\0support@github.com\0deps: bump\0\n"
    )
    monkeypatch.setattr(contributions.base, "git", lambda *_args, **_kwargs: raw)
    records = contributions._parse_log(10)
    assert [record["sha"] for record in records] == ["a" * 40, "b" * 40]
    assert records[0]["subject"] == "Title"
    assert "Co-authored-by" in records[0]["body"]


def test_build_separates_direct_credit_from_surface_mentions(monkeypatch) -> None:
    registry = {
        "schema": 1,
        "history_commit_limit": 100,
        "direct_trailer_keys": ["co-authored-by", "assisted-by"],
        "informational_trailer_keys": ["signed-off-by"],
        "actors": [
            {
                "id": "human:owner",
                "display_name": "Owner",
                "kind": "human",
                "aliases": ["Owner"],
                "identity_patterns": ["owner@example.test"],
                "evidence_class": "repository-observed",
            },
            {
                "id": "ai:copilot",
                "display_name": "Copilot",
                "kind": "ai-agent",
                "aliases": ["Copilot App"],
                "identity_patterns": ["copilot@example.test"],
                "instruction_files": ["COPILOT.md"],
                "evidence_class": "repository-observed",
            },
            {
                "id": "ai:grok",
                "display_name": "Grok",
                "kind": "ai-agent",
                "aliases": ["Grok"],
                "surface_terms": ["grok"],
                "evidence_class": "user-declared-and-repository-surface",
            },
        ],
        "semantics": {},
    }
    records = [
        {
            "sha": "1" * 40,
            "author_name": "Owner",
            "author_email": "owner@example.test",
            "committer_name": "Owner",
            "committer_email": "owner@example.test",
            "body": "Use grok notes\n\nCo-authored-by: Copilot App <copilot@example.test>",
            "subject": "Use grok notes",
        }
    ]
    monkeypatch.setattr(contributions, "_registry", lambda: registry)
    monkeypatch.setattr(contributions, "_parse_log", lambda _limit: records)
    monkeypatch.setattr(contributions.base, "git", lambda *args, **kwargs: "1" if args[:2] == ("rev-list", "--count") else "")
    snapshot = {"files": [{"path": "COPILOT.md"}, {"path": "src/app.py"}]}
    payload = contributions.build(snapshot)
    actors = {actor["id"]: actor for actor in payload["actors"]}
    assert actors["ai:copilot"]["explicit_direct_trailer_commits"] == 1
    assert actors["ai:copilot"]["direct_commit_participation"] == 1
    assert actors["ai:grok"]["direct_commit_participation"] == 0
    assert actors["ai:grok"]["commit_message_reference_count"] == 1
    assert actors["ai:copilot"]["instruction_files_present"] == ["COPILOT.md"]


def test_unknown_bot_identity_is_not_aliased_to_named_service(monkeypatch) -> None:
    registry = {
        "schema": 1,
        "history_commit_limit": 100,
        "direct_trailer_keys": ["co-authored-by"],
        "informational_trailer_keys": [],
        "actors": [],
        "semantics": {},
    }
    records = [
        {
            "sha": "2" * 40,
            "author_name": "mystery-agent[bot]",
            "author_email": "999+mystery-agent[bot]@users.noreply.github.com",
            "committer_name": "mystery-agent[bot]",
            "committer_email": "999+mystery-agent[bot]@users.noreply.github.com",
            "body": "automated change",
            "subject": "automated change",
        }
    ]
    monkeypatch.setattr(contributions, "_registry", lambda: registry)
    monkeypatch.setattr(contributions, "_parse_log", lambda _limit: records)
    monkeypatch.setattr(contributions.base, "git", lambda *args, **kwargs: "1" if args[:2] == ("rev-list", "--count") else "")
    payload = contributions.build({"files": []})
    assert len(payload["unknown_direct_identities"]) == 1
    unknown = payload["unknown_direct_identities"][0]
    assert unknown["kind"] == "bot-like"
    assert unknown["id"].startswith("unknown-bot:")


def test_contract_file_is_present() -> None:
    assert (ROOT / "repo-intel" / "contributors.json").is_file()
