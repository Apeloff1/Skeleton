import json

from core.shift_supervisor.workforce_report import idle_snapshot, night_snapshot


def test_idle_snapshot_accounts_for_all_four_squad_roles(tmp_path):
    package = tmp_path / "package.json"
    audit = tmp_path / "audit.jsonl"
    package.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "task": {"key": "issue:42"},
                        "researcher": {"worker_id": "idle-0010", "role": "research-benchmark"},
                        "builder": {"worker_id": "idle-0042", "role": "backend"},
                        "reviewer": {"worker_id": "idle-0900", "role": "security"},
                        "verifier": {"worker_id": "idle-0800", "role": "testing"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    audit.write_text('{"ts":"2026-09-16T10:00:00+00:00","event":"state"}\n', encoding="utf-8")

    snapshot = idle_snapshot(package, audit)

    assert snapshot["team"] == "idle"
    workers = {worker["worker_id"]: worker for worker in snapshot["workers"]}
    assert set(workers) == {"idle-0010", "idle-0042", "idle-0800", "idle-0900"}
    assert all(worker["metadata"]["worked_on"] == ["issue:42"] for worker in workers.values())
    assert workers["idle-0010"]["metadata"]["roles"] == ["research-benchmark"]
    assert workers["idle-0042"]["metadata"]["roles"] == ["backend"]
    assert workers["idle-0800"]["metadata"]["roles"] == ["testing"]
    assert workers["idle-0900"]["metadata"]["roles"] == ["security"]
    assert all(worker["status"] == "offline" for worker in workers.values())


def test_idle_snapshot_remains_compatible_with_legacy_two_agent_entry(tmp_path):
    package = tmp_path / "package.json"
    audit = tmp_path / "audit.jsonl"
    package.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "task": {"key": "legacy:1"},
                        "builder": {"worker_id": "idle-build", "role": "backend"},
                        "reviewer": {"worker_id": "idle-review", "role": "security"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    audit.write_text('{"ts":"2026-09-16T10:00:00+00:00","event":"state"}\n', encoding="utf-8")

    snapshot = idle_snapshot(package, audit)

    assert {worker["worker_id"] for worker in snapshot["workers"]} == {"idle-build", "idle-review"}


def test_night_snapshot_accounts_for_all_four_accepted_patch_workers(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                '{"ts":"2026-09-16T10:00:00+00:00","event":"run_started"}',
                '{"ts":"2026-09-16T10:03:00+00:00","event":"patch_rejected_by_squad","task":"skip","researcher":"skip-research","builder":"skip-build","reviewer":"skip-review","verifier":"skip-verify"}',
                '{"ts":"2026-09-16T10:05:00+00:00","event":"patch_accepted","task":"task-a","researcher":"night-research-2","builder":"night-build-7","reviewer":"night-review-3","verifier":"night-verify-4"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = night_snapshot(audit)

    assert snapshot["team"] == "night"
    workers = {worker["worker_id"]: worker for worker in snapshot["workers"]}
    assert set(workers) == {"night-research-2", "night-build-7", "night-review-3", "night-verify-4"}
    assert workers["night-research-2"]["metadata"]["roles"] == ["researcher"]
    assert workers["night-build-7"]["metadata"]["roles"] == ["builder"]
    assert workers["night-review-3"]["metadata"]["roles"] == ["reviewer"]
    assert workers["night-verify-4"]["metadata"]["roles"] == ["verifier"]
    assert all(worker["metadata"]["worked_on"] == ["task-a"] for worker in workers.values())


def test_night_snapshot_ignores_rejected_squad_workers(tmp_path):
    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                '{"ts":"2026-09-16T10:00:00+00:00","event":"run_started"}',
                '{"ts":"2026-09-16T10:03:00+00:00","event":"patch_rejected_by_squad","task":"skip","researcher":"skip-research","builder":"skip-build","reviewer":"skip-review","verifier":"skip-verify"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = night_snapshot(audit)

    assert snapshot["workers"] == []
