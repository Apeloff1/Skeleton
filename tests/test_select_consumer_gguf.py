"""Specialist diagnostic selection uses synthetic—not physical—receipts."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import compare_consumer_gguf as diagnostic
from scripts import select_consumer_gguf as selector


def report():
    profiles = [
        diagnostic.Profile("a", Path("a.json"), "a"*64, "b"*64, "c"*64, "a", "1"*64),
        diagnostic.Profile("b", Path("b.json"), "d"*64, "e"*64, "f"*64, "b", "2"*64),
    ]
    tasks = {task.prompt: task for task in diagnostic._TASKS}
    by_manifest = {p.manifest: p for p in profiles}
    def fake(path, *, prompt, max_output_tokens, expected_manifest_sha256):
        p = by_manifest[path]
        task = tasks[prompt]
        answer = task.exact if p.label == "a" or task.category == "code" else "wrong"
        receipt = dict(schema_version=diagnostic.QUALIFICATION_SCHEMA, status="qualified",
                       provider="local", manifest_sha256=p.manifest_sha256,
                       model_sha256=p.model_sha256, executable_sha256=p.executable_sha256,
                       model_id=p.model_id, prompt_sha256=diagnostic._text_digest(prompt),
                       output_sha256=diagnostic._text_digest(answer), network_required=False,
                       hosted_provider_credentials_required=False)
        receipt["receipt_digest"] = diagnostic._digest(receipt)
        return receipt
    return diagnostic.compare(profiles, repeats=2, qualify=fake)


def reseal(data):
    data.pop("report_sha256", None)
    data["report_sha256"] = diagnostic._digest(data)
    return data


def test_specialist_selection_never_activates():
    result = selector.select(report())
    assert result["activation_authorized"] is False
    assert result["categories"]["reasoning"]["preferred"]["profile"] == "a"
    assert result["categories"]["code"]["distinct_weight_alternative"] is not None
    assert len(result["categories"]["grounding"]["excluded"]) == 1


def test_no_distinct_weight_alternative_for_same_weights():
    result = report()
    result["profiles"][1]["model_sha256"] = result["profiles"][0]["model_sha256"]
    chosen = selector.select(reseal(result))
    assert chosen["categories"]["code"]["distinct_weight_alternative"] is None


@pytest.mark.parametrize("fault", ["digest", "missing", "duplicate", "foreign", "scorer", "repeat"])
def test_invalid_evidence_denied(fault):
    result = report()
    if fault == "digest":
        result["planned_attempts"] = 0
    elif fault == "missing":
        result["rows"].pop()
    elif fault == "duplicate":
        result["rows"][-1] = copy.deepcopy(result["rows"][0])
    elif fault == "foreign":
        result["rows"][0]["task"] = "other-task"
    elif fault == "scorer":
        result["scorer_source_sha256"] = "0"*64
    else:
        result["repeats"] = 1
    if fault != "digest":
        reseal(result)
    with pytest.raises(ValueError):
        selector.select(result)


def test_incomplete_profile_cannot_win_specialist_route():
    data = report()
    row = next(r for r in data["rows"] if r["profile"] == "a")
    row.update(status="execution_failed", receipt_sha256=None)
    selected = selector.select(reseal(data))
    assert selected["categories"]["reasoning"]["preferred"] is None
    assert selected["categories"]["code"]["preferred"]["profile"] == "b"


def test_exact_report_file_pin(tmp_path):
    path = tmp_path / "report.json"
    raw = json.dumps(report()).encode()
    path.write_bytes(raw)
    assert selector.read_report(path, hashlib.sha256(raw).hexdigest())["status"] == "advisory_only"
    with pytest.raises(ValueError, match="pin"):
        selector.read_report(path, "0"*64)
