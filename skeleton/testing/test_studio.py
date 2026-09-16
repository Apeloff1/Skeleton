from __future__ import annotations

import json

import pytest

from skeleton.automation.studio import (
    BOT_COUNT,
    MAX_ACTIVE_COHORT,
    AuditEvent,
    ProposedFile,
    append_audit_event,
    build_registry,
    manifest_payload,
    parse_proposal_json,
    select_cohort,
    validate_proposal,
)


def test_registry_contains_exactly_1000_unique_specialists() -> None:
    roles = build_registry()

    assert len(roles) == BOT_COUNT == 1000
    assert len({role.bot_id for role in roles}) == 1000
    assert len({(role.domain, role.discipline, role.lane) for role in roles}) == 1000
    assert {role.risk_budget for role in roles} == {"read-only", "proposal-only"}


def test_manifest_is_machine_readable_and_matches_registry() -> None:
    payload = manifest_payload()

    assert payload["schema_version"] == 1
    assert payload["bot_count"] == 1000
    assert payload["max_active_cohort"] == MAX_ACTIVE_COHORT
    assert len(payload["roles"]) == 1000


def test_cohort_is_deterministic_bounded_and_rotates() -> None:
    first = select_cohort("2026-09-16-night", 32)
    same = select_cohort("2026-09-16-night", 32)
    next_run = select_cohort("2026-09-17-night", 32)

    assert first == same
    assert first != next_run
    assert len(first) == 32
    assert len({role.bot_id for role in first}) == 32


@pytest.mark.parametrize("size", [0, -1, MAX_ACTIVE_COHORT + 1, True])
def test_cohort_rejects_unsafe_sizes(size) -> None:
    with pytest.raises(ValueError):
        select_cohort("run", size)


def test_normal_code_and_docs_proposal_is_accepted() -> None:
    decision = validate_proposal(
        (
            ProposedFile("skeleton/gaming/new_system.py", "VALUE = 1\n"),
            ProposedFile("skeleton/testing/test_new_system.py", "def test_value():\n    assert 1 == 1\n"),
            ProposedFile("docs/game-building.md", "# Game building\n"),
        )
    )

    assert decision.accepted is True
    assert decision.files == 3
    assert decision.bytes > 0
    assert len(decision.fingerprint) == 64


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/owned.yml",
        ".github/actions/owned/action.yml",
        ".env",
        "pyproject.toml",
        "security/policy.py",
        "auth/session.py",
        "../escape.py",
        "/tmp/escape.py",
        "skeleton/credential_store.py",
    ],
)
def test_sensitive_or_noncanonical_paths_are_rejected(path: str) -> None:
    decision = validate_proposal((ProposedFile(path, "x = 1\n"),))

    assert decision.accepted is False
    assert decision.reasons


def test_duplicate_and_oversized_bundles_fail_closed() -> None:
    duplicate = validate_proposal(
        (
            ProposedFile("skeleton/gaming/a.py", "x=1\n"),
            ProposedFile("skeleton/gaming/a.py", "x=2\n"),
        )
    )
    too_many = validate_proposal(
        tuple(ProposedFile(f"skeleton/gaming/f{i}.py", "x=1\n") for i in range(9))
    )
    huge = validate_proposal((ProposedFile("skeleton/gaming/huge.py", "x" * 80_001),))

    assert duplicate.accepted is False
    assert "duplicate path: skeleton/gaming/a.py" in duplicate.reasons
    assert too_many.accepted is False
    assert "too many files" in too_many.reasons
    assert huge.accepted is False
    assert "file too large: skeleton/gaming/huge.py" in huge.reasons


def test_model_proposal_parser_accepts_only_narrow_json_contract() -> None:
    parsed = parse_proposal_json(
        json.dumps({"files": [{"path": "skeleton/gaming/a.py", "content": "x=1\n"}]})
    )

    assert parsed == (ProposedFile("skeleton/gaming/a.py", "x=1\n"),)

    with pytest.raises(ValueError):
        parse_proposal_json('{"files": [], "command": "rm -rf /"}')
    with pytest.raises(ValueError):
        parse_proposal_json('{"files":[{"path":"a","content":"b","shell":"whoami"}]}')
    with pytest.raises(ValueError):
        parse_proposal_json("not-json")


def test_audit_log_is_append_only_jsonl(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    first = AuditEvent("2026-09-16T00:00:00+00:00", "run-1", "studio-0001", "plan", "planned", "one", "a")
    second = AuditEvent("2026-09-16T00:01:00+00:00", "run-1", "studio-0002", "review", "passed", "two", "b")

    append_audit_event(path, first)
    append_audit_event(path, second)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["bot_id"] for row in rows] == ["studio-0001", "studio-0002"]
    assert [row["status"] for row in rows] == ["planned", "passed"]
