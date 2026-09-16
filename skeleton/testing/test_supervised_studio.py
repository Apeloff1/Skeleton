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
