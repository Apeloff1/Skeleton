"""Hermetic source tests; fake receipts are not native inference evidence."""
from pathlib import Path

import pytest

from scripts import compare_consumer_gguf as mod


def _profiles():
    return [
        mod.Profile("baseline", Path("baseline.json"), "a"*64, "b"*64, "c"*64, "base", "1"*64),
        mod.Profile("candidate", Path("candidate.json"), "d"*64, "e"*64, "f"*64, "cand", "2"*64),
    ]


def _qualifier(profiles, *, different=False, drift=False, corrupt=False):
    by_path = {p.manifest: p for p in profiles}
    by_prompt = {task.prompt: task for task in mod._TASKS}
    calls = []
    def qualify(path, *, prompt, max_output_tokens, expected_manifest_sha256):
        p = by_path[path]
        assert expected_manifest_sha256 == p.manifest_file_sha256
        calls.append((p.label, prompt))
        task = by_prompt[prompt]
        assert max_output_tokens == task.max_tokens
        output = "wrong" if different and p.label == "baseline" else task.exact
        receipt = {
            "schema_version": mod.QUALIFICATION_SCHEMA, "status": "qualified",
            "provider": "local", "network_required": False,
            "hosted_provider_credentials_required": False,
            "manifest_sha256": p.manifest_sha256, "model_sha256": p.model_sha256,
            "executable_sha256": p.executable_sha256, "model_id": p.model_id,
            "prompt_sha256": mod._text_digest(prompt),
            "output_sha256": mod._text_digest(output),
        }
        if drift and p.label == "candidate":
            receipt["model_sha256"] = "0"*64
        receipt["receipt_digest"] = mod._digest(receipt)
        if corrupt and p.label == "candidate":
            receipt["output_sha256"] = "0"*64
        return receipt
    return qualify, calls


def test_matched_diagnostic_all_tasks_and_rotation():
    profiles = _profiles()
    qualify, calls = _qualifier(profiles, different=True)
    report = mod.compare(profiles, repeats=2, qualify=qualify)
    assert report["planned_attempts"] == len(report["rows"]) == 48
    assert report["summaries"]["candidate"]["exact"] == 24
    assert report["summaries"]["baseline"]["native_completed"] == 24
    assert report["summaries"]["baseline"]["exact"] == 0
    assert report["paired"]["candidate"]["exact_wins"] == 24
    assert report["paired"]["candidate"]["jointly_exact"] == 0
    assert [c[0] for c in calls[:4]] == ["baseline", "candidate", "candidate", "baseline"]
    digest = report.pop("report_sha256")
    assert digest == mod._digest(report)
    assert report["status"] == "advisory_only"
    assert "baseline.json" not in str(report)


@pytest.mark.parametrize("fault", ["drift", "corrupt"])
def test_identity_fault_holds_remaining_candidate_work(fault):
    profiles = _profiles()
    qualify, calls = _qualifier(profiles, **{fault: True})
    report = mod.compare(profiles, qualify=qualify)
    assert report["identity_holds"] == ["candidate"]
    assert sum(label == "candidate" for label, _ in calls) == 1
    assert report["summaries"]["candidate"]["failed"] == 12
    assert report["summaries"]["baseline"]["exact"] == 12
    assert report["paired"]["candidate"]["exact_losses"] == 0
    assert report["paired"]["candidate"]["unmatched_attempt_pairs"] == 12


def test_failure_counted_and_no_false_exact():
    profiles = _profiles()
    def fail(*args, **kwargs):
        raise mod.LocalModelDeploymentError("private path")
    report = mod.compare(profiles, qualify=fail)
    assert report["summaries"]["baseline"]["failed"] == 12
    assert report["summaries"]["baseline"]["median_completed_wall_seconds"] is None
    assert "private path" not in str(report)


def test_deadline_records_missing_work_without_claiming_success():
    profiles = _profiles()
    qualify, calls = _qualifier(profiles)
    ticks = iter([0, 2] + [2]*100)
    report = mod.compare(profiles, deadline_seconds=1, qualify=qualify, clock=lambda: next(ticks))
    assert not calls
    assert {row["status"] for row in report["rows"]} == {"not_started_deadline"}
    assert report["planned_attempts"] == 24


@pytest.mark.parametrize("repeats", [0, 4, True])
def test_repeats_bounded(repeats):
    with pytest.raises(ValueError, match="repeats"):
        mod.compare(_profiles(), repeats=repeats)


def test_duplicate_profiles_denied():
    profile = _profiles()[0]
    with pytest.raises(ValueError, match="distinct"):
        mod.compare([profile, profile])
