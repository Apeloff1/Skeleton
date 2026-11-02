"""End-to-end consumer source-level cohort acceptance and adversarial custody tests."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.consumer_first_run_cohort import (
    ConsumerFirstRunCohortError, inspect_consumer_first_run_cohort,
    inspect_pinned_consumer_cohort,
)
from skeleton.app.offline_first_playable_batch import (
    publish_first_playable_delivery_batch,
)
from skeleton.testing.test_app_offline_first_playable_batch import (
    jobs_for, original_games, pinned,
)
from skeleton.testing.test_app_offline_first_playable_jobfile import _file


@pytest.fixture(scope="module")
def delivered_games(original_games, tmp_path_factory):
    root = tmp_path_factory.mktemp("consumer-first-run-cohort")
    jobs = jobs_for(original_games, root)
    summary = root / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    return pinned(jobs, published), summary, published


def test_real_two_game_install_play_save_restore_and_consumer_readiness(
    delivered_games,
):
    jobs, summary, published = delivered_games
    before = tuple(
        (Path(job.archive).read_bytes(), Path(job.save).read_bytes(),
         Path(job.receipt).read_bytes())
        for job in jobs
    )
    result = inspect_consumer_first_run_cohort(
        jobs, summary,
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True,
    )
    assert result["status"] == "consumer_source_level_cohort_replayed_release_blocked"
    assert result["game_count"] == 2
    assert result["all_installed_games_and_private_saves_reexecuted"] is True
    assert result["canonical_cohort_inspections"] == 2
    assert result["source_level_replay_passes_per_game"] == 2
    assert result["cohort_and_job_inodes_stable"] is False
    assert result["root_and_evidence_inodes_stable"] is True
    assert result["nested_asset_inode_inventory_attested"] is True
    assert result["nested_asset_inode_snapshots_equal"] is True
    assert all(len(game["installed_tree_snapshot_sha256"]) == 64
               for game in result["games"])
    assert result["private_jobfile_inode_attested"] is False
    assert result["read_only"] is True
    assert result["files_published"] == 0
    assert result["release_holds"]
    for key in (
        "native_device_qualified", "native_godot_executed",
        "windows_laptop_qualified", "installer_qualified",
        "guarded_local_ai_qualified", "package_signed", "rights_certified",
        "persistent_rollback_protection", "release_certified",
    ):
        assert result[key] is False
    assert [game["project_id"] for game in result["games"]] == [
        game["project_id"] for game in published["games"]
    ]
    assert all(game["source_level_replay_passes"] == 2 for game in result["games"])
    after = tuple(
        (Path(job.archive).read_bytes(), Path(job.save).read_bytes(),
         Path(job.receipt).read_bytes())
        for job in jobs
    )
    assert before == after
    assert sha256(summary.read_bytes()).hexdigest() == published["independent_summary_sha256"]


def test_cli_pinned_private_jobfile_and_explicit_release_holds(
    delivered_games, tmp_path, capsys,
):
    jobs, summary, published = delivered_games
    jobfile, job_pin = _file(tmp_path, jobs)
    base = [
        "consumer-first-run-cohort", "--jobs-file", str(jobfile),
        "--expected-jobs-sha256", job_pin,
        "--summary", str(summary),
        "--expected-summary-sha256", published["independent_summary_sha256"],
    ]
    assert run_app_cli(base) == 2
    denied = json.loads(capsys.readouterr().err)
    assert denied["status"] == "blocked"
    assert denied["release_certified"] is False
    assert run_app_cli(base + ["--trusted-local-operator"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["game_count"] == 2
    assert report["independent_jobs_sha256"] == job_pin
    assert report["private_jobfile_inode_attested"] is True
    assert report["native_device_qualified"] is False
    assert report["release_certified"] is False
    assert report["files_published"] == 0
    assert report["original_sources_reverified"] is False
    assert run_app_cli(base + [
        "--trusted-local-operator", "--verify-original-sources",
    ]) == 0
    source_bound = json.loads(capsys.readouterr().out)
    assert source_bound["original_sources_reverified"] is True
    assert source_bound["release_certified"] is False


def test_wrong_independent_pins_and_partial_game_pins_fail_closed(
    delivered_games, tmp_path,
):
    jobs, summary, published = delivered_games
    with pytest.raises(ConsumerFirstRunCohortError):
        inspect_consumer_first_run_cohort(
            jobs, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True, verify_original_sources="yes",
        )
    with pytest.raises(ValueError):
        inspect_consumer_first_run_cohort(
            jobs, summary, expected_summary_sha256="0" * 64,
            authorized=True,
        )
    with pytest.raises(ValueError):
        inspect_consumer_first_run_cohort(
            jobs, summary,
            expected_summary_sha256="A" * 64,
            authorized=True,
        )
    incomplete = (replace(jobs[0], receipt_sha256=None), jobs[1])
    with pytest.raises(ValueError):
        inspect_consumer_first_run_cohort(
            incomplete, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
    jobfile, job_pin = _file(tmp_path, jobs)
    with pytest.raises(ValueError):
        inspect_pinned_consumer_cohort(
            jobfile, expected_jobs_sha256="0" * 64,
            summary=summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
    assert job_pin != "0" * 64


def test_same_byte_receipt_inode_substitution_during_cross_game_replay(
    delivered_games, tmp_path, monkeypatch,
):
    from skeleton.app import consumer_first_run_cohort as module

    jobs, summary, published = delivered_games
    original = module.inspect_consumer_first_run
    swapped = False
    # Never modify the shared fixture: use an isolated copy of the receipt
    # and its original independently pinned bytes to simulate a live swap.
    # A copied receipt is a different inode from the start but still valid.
    replacement = tmp_path / "receipt-0.json"
    replacement.write_bytes(Path(jobs[0].receipt).read_bytes())
    replacement.chmod(0o600)
    copy_jobs = (replace(jobs[0], receipt=replacement), jobs[1])
    # The canonical summary binds the original paths only through content
    # records, so inspect the cloned receipt as an independently pinned job.
    def swap_after_first(*args, **kwargs):
        nonlocal swapped
        result = original(*args, **kwargs)
        if not swapped:
            swapped = True
            temporary = tmp_path / "new-receipt.json"
            temporary.write_bytes(replacement.read_bytes())
            temporary.chmod(0o600)
            os.replace(temporary, replacement)
        return result

    monkeypatch.setattr(module, "inspect_consumer_first_run", swap_after_first)
    with pytest.raises(ValueError):
        inspect_consumer_first_run_cohort(
            copy_jobs, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )


def test_forged_consumer_release_claim_is_rejected(
    delivered_games, monkeypatch,
):
    from skeleton.app import consumer_first_run_cohort as module

    jobs, summary, published = delivered_games
    original = module.inspect_consumer_first_run

    def forged(*args, **kwargs):
        return {**original(*args, **kwargs), "release_certified": True}

    monkeypatch.setattr(module, "inspect_consumer_first_run", forged)
    with pytest.raises(ConsumerFirstRunCohortError, match="diverged"):
        inspect_consumer_first_run_cohort(
            jobs, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )


def test_forged_nested_inode_inventory_digest_is_rejected(
    delivered_games, monkeypatch,
):
    from skeleton.app import consumer_first_run_cohort as module

    jobs, summary, published = delivered_games
    original = module.inspect_consumer_first_run

    def forged(*args, **kwargs):
        return {
            **original(*args, **kwargs),
            "installed_tree_snapshot_sha256": "Z" * 64,
        }

    monkeypatch.setattr(module, "inspect_consumer_first_run", forged)
    with pytest.raises(ConsumerFirstRunCohortError, match="diverged"):
        inspect_consumer_first_run_cohort(
            jobs, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
