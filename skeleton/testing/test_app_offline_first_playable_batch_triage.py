"""Read-only nofollow quarantine triage for interrupted playable delivery."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_first_playable_batch import (
    publish_first_playable_delivery_batch,
)
from skeleton.app.offline_first_playable_delivery import publish_first_playable_delivery
from skeleton.app.offline_first_playable_batch_triage import (
    triage_first_playable_delivery_batch,
)
from skeleton.testing.test_app_offline_first_playable_batch import (
    original_games, jobs_for, pinned,
)


def test_empty_cohort_is_pending_and_read_only(original_games, tmp_path):
    jobs = jobs_for(original_games, tmp_path)
    result = triage_first_playable_delivery_batch(
        jobs, tmp_path / "cohort.json", authorized=True,
    )
    assert [item["state"] for item in result["jobs"]] == [
        "missing_unpublished", "missing_unpublished",
    ]
    assert result["resume_eligible_with_independent_pins"] is False
    assert result["summary_state"] == "missing"
    assert result["read_only"] is True
    assert result["release_certified"] is False
    assert not Path(jobs[0].archive).exists()


def test_pinned_first_game_and_missing_second_is_resume_eligible(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    first = jobs[0]
    published = publish_first_playable_delivery(
        first.source, first.archive, first.install, first.save, first.receipt,
        expected_manifest_sha256=first.manifest_sha256,
        moves=first.moves, authorized=True,
    )
    checked = replace(
        first, archive_sha256=published["archive_sha256"],
        save_sha256=published["save_sha256"],
        receipt_sha256=published["independent_receipt_sha256"],
    )
    receipt_before = Path(first.receipt).read_bytes()
    result = triage_first_playable_delivery_batch(
        (checked, jobs[1]), tmp_path / "cohort.json", authorized=True,
    )
    assert result["verified_prefix_count"] == 1
    assert result["resume_eligible_with_independent_pins"] is True
    assert result["jobs"][0]["state"] == "independently_pinned_replay_verified"
    assert result["jobs"][1]["state"] == "missing_unpublished"
    assert Path(first.receipt).read_bytes() == receipt_before
    assert not Path(jobs[1].archive).exists()


def test_unpinned_partial_publication_requires_quarantine(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    Path(jobs[0].archive).write_bytes(b"untrusted")
    result = triage_first_playable_delivery_batch(
        jobs, tmp_path / "cohort.json", authorized=True,
    )
    assert result["jobs"][0]["state"] == "partial_publication_quarantine"
    assert result["resume_eligible_with_independent_pins"] is False
    assert Path(jobs[0].archive).read_bytes() == b"untrusted"


def test_symlinked_archive_is_unsafe_and_never_followed(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    victim = tmp_path / "victim.zip"
    victim.write_bytes(b"owner-data")
    Path(jobs[0].archive).symlink_to(victim)
    result = triage_first_playable_delivery_batch(
        jobs, tmp_path / "cohort.json", authorized=True,
    )
    assert result["jobs"][0]["state"] == "unsafe_custody_quarantine"
    assert result["resume_eligible_with_independent_pins"] is False
    assert victim.read_bytes() == b"owner-data"


def test_complete_cohort_requires_separately_held_summary_pin(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    unpinned = triage_first_playable_delivery_batch(
        pinned(jobs, published), summary, authorized=True,
    )
    assert unpinned["all_games_verified"] is True
    assert unpinned["summary_state"] == "untrusted_summary_missing_independent_pin"
    checked = triage_first_playable_delivery_batch(
        pinned(jobs, published), summary,
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True,
    )
    assert checked["summary_state"] == "independently_pinned_cohort_verified"
    assert checked["all_games_verified"] is True
    assert checked["release_certified"] is False


def test_cli_missing_authorization_blocks_without_touching_files(
    original_games, tmp_path, capsys,
):
    jobs = jobs_for(original_games, tmp_path)
    args = ["first-playable-batch-triage", "--summary", str(tmp_path / "cohort.json")]
    for job in jobs:
        args += ["--job", json.dumps({
            "source": str(job.source), "archive": str(job.archive),
            "install": str(job.install), "save": str(job.save),
            "receipt": str(job.receipt),
            "manifest_sha256": job.manifest_sha256,
            "moves": list(job.moves),
        })]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False
    assert run_app_cli(args + ["--trusted-local-operator"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["summary_state"] == "missing"
    assert result["read_only"] is True
    assert not Path(jobs[0].archive).exists()
