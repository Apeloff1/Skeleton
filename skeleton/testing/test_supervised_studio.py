from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

import skeleton.automation.supervised_studio as supervised_studio


def _repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Supervisor Smoke"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "supervisor@example.invalid"], cwd=tmp_path, check=True)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "smoke.txt").write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/smoke.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    runner = tmp_path.parent / f"{tmp_path.name}-runner"
    monkeypatch.setenv("RUNNER_TEMP", str(runner))
    state = tmp_path.parent / f"{tmp_path.name}-state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "gen-1",
                    "plan_items": [
                        {
                            "id": "night-plan-1",
                            "title": "Canonical smoke change",
                            "description": "Replace the smoke fixture value.",
                            "priority": 100,
                            "target_team": "night",
                            "status": "queued",
                            "expected_output": "Fixture says new.",
                            "validation": ["smoke test"],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    return state


def test_supervised_night_smoke_preserves_canonical_plan_id(tmp_path, monkeypatch):
    state = _repo(tmp_path, monkeypatch)
    responses = [
        json.dumps(
            {
                "plan_item_id": "night-plan-1",
                "division": "gameplay_systems",
                "paths": ["docs/smoke.txt"],
            }
        ),
        json.dumps(
            {
                "findings": ["docs/smoke.txt contains the old fixture value"],
                "risks": ["fixture must remain plain text"],
                "recommended_checks": ["git apply --check", "credential-free smoke"],
            }
        ),
        json.dumps(
            {
                "patch": (
                    "diff --git a/docs/smoke.txt b/docs/smoke.txt\n"
                    "--- a/docs/smoke.txt\n"
                    "+++ b/docs/smoke.txt\n"
                    "@@ -1 +1 @@\n"
                    "-old\n"
                    "+new\n"
                ),
                "summary": "Apply the canonical smoke task.",
                "tests": ["smoke"],
            }
        ),
        json.dumps({"approve": True, "reasons": ["bounded canonical task"]}),
        json.dumps(
            {
                "approve": True,
                "reasons": ["canonical task has deterministic validation"],
                "required_checks": ["credential-free autonomous studio smoke"],
            }
        ),
    ]

    class FakeReasoner:
        def __init__(self):
            self.index = 0

        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            text = responses[self.index]
            self.index += 1
            return SimpleNamespace(ok=True, text=text, error_kind=None)

    monkeypatch.setattr(supervised_studio, "ChatGPTReasoner", FakeReasoner)
    patch = tmp_path.parent / "proposal.patch"
    audit = tmp_path.parent / "audit.jsonl"

    assert supervised_studio.propose(
        patch_path=patch,
        audit_path=audit,
        repo_state_path=state,
        max_tasks=1,
        cohort_size=3,
        seed="canonical-smoke",
    ) == 0

    assert "+new" in patch.read_text(encoding="utf-8")
    assert (tmp_path / "docs/smoke.txt").read_text(encoding="utf-8") == "old\n"
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    accepted = next(row for row in rows if row["event"] == "patch_accepted")
    assert accepted["task"] == "night-plan-1"
    assert accepted["task_title"] == "Canonical smoke change"
    workers = {
        accepted["researcher"],
        accepted["builder"],
        accepted["reviewer"],
        accepted["verifier"],
    }
    assert len(workers) == 4
    assert accepted["required_checks"] == ["credential-free autonomous studio smoke"]
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""


def test_supervised_night_rejects_overlapping_scoped_paths(tmp_path, monkeypatch):
    state = _repo(tmp_path, monkeypatch)
    payload = json.loads(state.read_text(encoding="utf-8"))
    payload["_shift_supervisor"]["plan_items"].append(
        {
            "id": "night-plan-2",
            "title": "Second canonical smoke change",
            "description": "A second task that must not share the same file scope.",
            "priority": 90,
            "target_team": "night",
            "status": "queued",
            "expected_output": "Independent file scope.",
            "validation": ["smoke test"],
        }
    )
    state.write_text(json.dumps(payload), encoding="utf-8")
    responses = [
        json.dumps(
            {
                "plan_item_id": "night-plan-1",
                "division": "gameplay_systems",
                "paths": ["docs/smoke.txt"],
            }
        ),
        json.dumps(
            {
                "plan_item_id": "night-plan-2",
                "division": "gameplay_systems",
                "paths": ["docs/smoke.txt"],
            }
        ),
    ]

    class OverlapReasoner:
        def __init__(self):
            self.index = 0

        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            text = responses[self.index]
            self.index += 1
            return SimpleNamespace(ok=True, text=text, error_kind=None)

    monkeypatch.setattr(supervised_studio, "ChatGPTReasoner", OverlapReasoner)
    patch = tmp_path.parent / "overlap.patch"
    audit = tmp_path.parent / "overlap-audit.jsonl"

    with pytest.raises(ValueError, match="overlapping path"):
        supervised_studio.propose(
            patch_path=patch,
            audit_path=audit,
            repo_state_path=state,
            max_tasks=2,
            cohort_size=3,
            seed="overlap",
        )

    assert patch.read_text(encoding="utf-8") == ""
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "run_failed_closed"
    assert rows[-1]["stage"] == "supervisor_scope"


def test_supervised_night_requires_plan_generation(tmp_path, monkeypatch):
    state = _repo(tmp_path, monkeypatch)
    payload = json.loads(state.read_text(encoding="utf-8"))
    payload["_shift_supervisor"].pop("generation_id")
    state.write_text(json.dumps(payload), encoding="utf-8")

    class UnusedReasoner:
        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            raise AssertionError("model must not run without plan_generation")

    monkeypatch.setattr(supervised_studio, "ChatGPTReasoner", UnusedReasoner)
    patch = tmp_path.parent / "no-generation.patch"
    audit = tmp_path.parent / "no-generation-audit.jsonl"
    with pytest.raises(ValueError, match="plan_generation"):
        supervised_studio.propose(
            patch_path=patch,
            audit_path=audit,
            repo_state_path=state,
            max_tasks=1,
            cohort_size=3,
            seed="missing-generation",
        )


def test_supervised_night_records_plan_generation(tmp_path, monkeypatch):
    state = _repo(tmp_path, monkeypatch)
    original = state.read_bytes()
    responses = [
        json.dumps(
            {
                "plan_item_id": "night-plan-1",
                "division": "gameplay_systems",
                "paths": ["docs/smoke.txt"],
            }
        ),
        json.dumps(
            {
                "findings": ["docs/smoke.txt contains the old fixture value"],
                "risks": ["fixture must remain plain text"],
                "recommended_checks": ["git apply --check", "credential-free smoke"],
            }
        ),
        json.dumps(
            {
                "patch": (
                    "diff --git a/docs/smoke.txt b/docs/smoke.txt\n"
                    "--- a/docs/smoke.txt\n"
                    "+++ b/docs/smoke.txt\n"
                    "@@ -1 +1 @@\n"
                    "-old\n"
                    "+new\n"
                ),
                "summary": "Apply the canonical smoke task.",
                "tests": ["smoke"],
            }
        ),
        json.dumps({"approve": True, "reasons": ["bounded canonical task"]}),
        json.dumps(
            {
                "approve": True,
                "reasons": ["canonical task has deterministic validation"],
                "required_checks": ["credential-free autonomous studio smoke"],
            }
        ),
    ]

    class FakeReasoner:
        def __init__(self):
            self.index = 0

        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            text = responses[self.index]
            self.index += 1
            return SimpleNamespace(ok=True, text=text, error_kind=None)

    monkeypatch.setattr(supervised_studio, "ChatGPTReasoner", FakeReasoner)
    patch = tmp_path.parent / "generation.patch"
    audit = tmp_path.parent / "generation-audit.jsonl"
    assert supervised_studio.propose(
        patch_path=patch,
        audit_path=audit,
        repo_state_path=state,
        max_tasks=1,
        cohort_size=3,
        seed="generation-smoke",
    ) == 0
    assert state.read_bytes() == original
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    created = next(row for row in rows if row["event"] == "plan_created")
    assert created["plan_generation"] == "gen-1"
    accepted = next(row for row in rows if row["event"] == "patch_accepted")
    assert accepted["task"] == "night-plan-1"


def test_supervised_night_rejects_scope_mapper_that_changes_plan_id(tmp_path, monkeypatch):
    state = _repo(tmp_path, monkeypatch)

    class WrongPlanReasoner:
        @staticmethod
        def redact(value: str) -> str:
            return value

        def reason(self, _request):
            return SimpleNamespace(
                ok=True,
                text=json.dumps(
                    {
                        "plan_item_id": "invented-task",
                        "division": "gameplay_systems",
                        "paths": ["docs/smoke.txt"],
                    }
                ),
                error_kind=None,
            )

    monkeypatch.setattr(supervised_studio, "ChatGPTReasoner", WrongPlanReasoner)
    patch = tmp_path.parent / "failed.patch"
    audit = tmp_path.parent / "failed-audit.jsonl"

    with pytest.raises(RuntimeError):
        supervised_studio.propose(
            patch_path=patch,
            audit_path=audit,
            repo_state_path=state,
            max_tasks=1,
            cohort_size=3,
            seed="wrong-plan",
        )

    assert patch.read_text(encoding="utf-8") == ""
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["event"] == "run_failed_closed"
    assert rows[-1]["stage"] == "supervisor_scope"


def test_supervised_night_operator_pause_preempts_model_work(tmp_path, monkeypatch):
    state = _repo(tmp_path, monkeypatch)
    monkeypatch.setenv("SKELETON_AUTOMATION_PAUSED", "true")
    monkeypatch.setenv("SKELETON_AUTOMATION_HOLD_REASON", "maintenance")
    monkeypatch.delenv("SKELETON_AUTOMATION_QUARANTINED", raising=False)

    class UnusedReasoner:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("model reasoner must not be constructed while paused")

    monkeypatch.setattr(supervised_studio, "ChatGPTReasoner", UnusedReasoner)
    patch = tmp_path.parent / "paused.patch"
    audit = tmp_path.parent / "paused-audit.jsonl"

    assert supervised_studio.propose(
        patch_path=patch,
        audit_path=audit,
        repo_state_path=state,
        max_tasks=1,
        cohort_size=3,
        seed="paused",
    ) == 0

    assert patch.read_text(encoding="utf-8") == ""
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    blocked = rows[-1]
    assert blocked["event"] == "run_blocked_by_operator"
    assert blocked["hold_status"] == "paused"
    assert blocked["reason"] == "maintenance"


def test_canonical_items_tolerates_malformed_priority_and_clamps_order(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "gen-priority",
                    "plan_items": [
                        {"id": "bad", "title": "Bad priority", "description": "Fallback.", "priority": "oops"},
                        {"id": "high", "title": "High priority", "description": "First.", "priority": 999},
                        {"id": "low", "title": "Low priority", "description": "Last.", "priority": -100},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    items, generation = supervised_studio._canonical_items(state, 3)
    assert generation == "gen-priority"
    assert [item["id"] for item in items] == ["high", "bad", "low"]


def test_canonical_items_rejects_duplicate_ids(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "gen-duplicate",
                    "plan_items": [
                        {"id": "same", "title": "One", "description": "One."},
                        {"id": "same", "title": "Two", "description": "Two."},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate plan item ids"):
        supervised_studio._canonical_items(state, 2)


def test_canonical_items_rejects_invalid_json_with_stable_error(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        supervised_studio._canonical_items(state, 1)


def test_canonical_items_rejects_oversized_snapshot(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(" " * 5_000_001, encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds 5 MB"):
        supervised_studio._canonical_items(state, 1)


def test_canonical_items_rejects_plan_digest_tampering(tmp_path):
    import hashlib

    items = [{"id": "one", "title": "One", "description": "Original", "priority": 50}]
    digest = hashlib.sha256(
        json.dumps(items, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    items[0]["description"] = "Tampered"
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "gen-tamper",
                    "plan_digest_sha256": digest,
                    "plan_items": items,
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="plan digest mismatch"):
        supervised_studio._canonical_items(state, 1)


def test_canonical_items_rejects_malformed_generation_identity(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "../escape",
                    "plan_items": [{"id": "one", "title": "One", "description": "One"}],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="generation id is malformed"):
        supervised_studio._canonical_items(state, 1)


def test_canonical_items_rejects_unbounded_plan_item_identity(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "safe-generation",
                    "plan_items": [{"id": "x" * 161, "title": "One", "description": "One"}],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exceeds 160"):
        supervised_studio._canonical_items(state, 1)


def test_canonical_items_rejects_malformed_digest(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "safe",
                    "plan_digest_sha256": "not-a-sha256",
                    "plan_items": [{"id": "one", "title": "One", "description": "One"}],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="digest is malformed"):
        supervised_studio._canonical_items(state, 1)


def test_canonical_items_rejects_unbounded_plan_count(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "_shift_supervisor": {
                    "status": "loaded",
                    "team": "night",
                    "generation_id": "safe",
                    "plan_items": [
                        {"id": f"item-{index}", "title": "T", "description": "D"}
                        for index in range(257)
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exceeds 256 plan items"):
        supervised_studio._canonical_items(state, 1)


def test_execution_receipt_is_deterministic_and_patch_bound():
    from skeleton.automation.studio_director import PlannedTask

    task = PlannedTask(
        title="Receipt",
        objective="Bind exact execution.",
        division="qa_verification",
        paths=("docs/example.md",),
    )
    kwargs = dict(
        run_id="run-1",
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed",
        scoped=[("plan-1", task)],
        patch="diff-body",
        accepted=1,
    )
    first = supervised_studio._execution_receipt(**kwargs)
    second = supervised_studio._execution_receipt(**kwargs)
    assert first == second
    assert first["patch_sha256"] == hashlib.sha256(b"diff-body").hexdigest()
    assert len(first["receipt_sha256"]) == 64

    changed = supervised_studio._execution_receipt(**{**kwargs, "patch": "different"})
    assert changed["receipt_sha256"] != first["receipt_sha256"]


def test_replay_key_binds_generation_plan_registry_and_seed():
    first = supervised_studio._replay_key(
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed-1",
    )
    assert len(first) == 64
    assert first == supervised_studio._replay_key(
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed-1",
    )
    assert first != supervised_studio._replay_key(
        generation_id="gen-2",
        plan_digest="a" * 64,
        seed="seed-1",
    )
    assert first != supervised_studio._replay_key(
        generation_id="gen-1",
        plan_digest="b" * 64,
        seed="seed-1",
    )
    assert first != supervised_studio._replay_key(
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed-2",
    )


def test_verify_execution_receipt_rejects_mutation():
    from skeleton.automation.studio_director import PlannedTask

    receipt = supervised_studio._execution_receipt(
        run_id="run-1",
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed",
        scoped=[(
            "plan-1",
            PlannedTask(
                title="Receipt",
                objective="Bind execution.",
                division="qa_verification",
                paths=("docs/example.md",),
            ),
        )],
        patch="patch",
        accepted=1,
    )
    supervised_studio.verify_execution_receipt(receipt)
    receipt["patch_chars"] = 999
    with pytest.raises(ValueError, match="digest mismatch"):
        supervised_studio.verify_execution_receipt(receipt)


def test_execution_receipt_contains_replay_key():
    from skeleton.automation.studio_director import PlannedTask

    receipt = supervised_studio._execution_receipt(
        run_id="run-1",
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed",
        scoped=[(
            "plan-1",
            PlannedTask(
                title="Receipt",
                objective="Bind execution.",
                division="qa_verification",
                paths=("docs/example.md",),
            ),
        )],
        patch="patch",
        accepted=1,
    )
    assert receipt["replay_key_sha256"] == supervised_studio._replay_key(
        generation_id="gen-1",
        plan_digest="a" * 64,
        seed="seed",
    )
