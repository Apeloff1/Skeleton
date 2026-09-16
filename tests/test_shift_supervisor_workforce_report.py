import json

from core.shift_supervisor.workforce_report import idle_snapshot, night_snapshot


def test_idle_snapshot_uses_package_builder_and_reviewer(tmp_path):
    package = tmp_path / "package.json"
    audit = tmp_path / "audit.jsonl"
    package.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "task": {"key": "issue:42"},
                        "builder": {"worker_id": "idle-0042", "role": "backend"},
                        "reviewer": {"worker_id": "idle-0900", "role": "security"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    audit.write_text('{"ts":"2026-09-16T10:00:00+00:00","event":"state"}\n', encoding="utf-8")

    snapshot = idle_snapshot(package, audit)

    assert snapshot["team"] == "idle"
    assert [worker["worker_id"] for worker in snapshot["workers"]] == ["idle-0042", "idle-0900"]
    worker = snapshot["workers"][0]
    assert worker["metadata"]["worked_on"] == ["issue:42"]
    assert worker["status"] == "offline"
    assert worker["metadata"]["shift_minutes"] == 1
    assert worker["metadata"]["shift_key"].startswith("idle:idle-0042:")
    assert worker["metadata"]["time_basis"] == "run-envelope"


def test_night_snapshot_uses_only_accepted_patch_workers(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                '{"ts":"2026-09-16T10:00:00+00:00","event":"run_started"}',
                '{"ts":"2026-09-16T10:03:00+00:00","event":"patch_rejected_by_reviewer","task":"skip"}',
                '{"ts":"2026-09-16T10:05:00+00:00","event":"patch_accepted","task":"task-a","builder":"night-build-7","reviewer":"night-review-3"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = night_snapshot(audit)

    assert snapshot["team"] == "night"
    workers = {worker["worker_id"]: worker for worker in snapshot["workers"]}
    assert set(workers) == {"night-build-7", "night-review-3"}
    assert workers["night-build-7"]["metadata"]["worked_on"] == ["task-a"]
    assert workers["night-review-3"]["metadata"]["roles"] == ["reviewer"]
    assert workers["night-build-7"]["metadata"]["shift_minutes"] == 5
    assert workers["night-build-7"]["normal_shift_minutes"] == 5
    assert workers["night-build-7"]["metadata"]["shift_key"].startswith(
        "night:night-build-7:2026-09-16T10:00:00+00:00:"
    )