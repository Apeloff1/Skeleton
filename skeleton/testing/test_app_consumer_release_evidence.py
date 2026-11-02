"""Consumer release gate integration: real game replay and fail-closed claims."""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.consumer_release_evidence import (
    ConsumerReleaseEvidenceError,
    inspect_cohort_consumer_release_hold,
    inspect_single_consumer_release_hold,
)
from skeleton.testing.test_app_consumer_first_run_readiness import delivered_first_run
from skeleton.testing.test_app_consumer_first_run_cohort import delivered_games
from skeleton.testing.test_app_offline_first_playable_delivery import original_source
from skeleton.testing.test_app_offline_first_playable_batch import original_games
from skeleton.testing.test_app_offline_first_playable_jobfile import _file


def test_real_single_game_installed_replayed_and_release_remains_blocked(
    delivered_first_run,
):
    paths, pins = delivered_first_run
    report = inspect_single_consumer_release_hold(*paths, **pins)
    evidence = report["source_level_evidence"]
    raw = json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    assert report["source_level_evidence_sha256"] == sha256(raw).hexdigest()
    assert report["mode"] == "single"
    assert evidence["source_level_replay_passes"] == 2
    assert evidence["installed_game_and_private_save_reexecuted"] is True
    assert report["release_holds"] == evidence["release_holds"]
    assert report["read_only"] is True
    assert report["files_published"] == 0
    for key in (
        "device_evidence_verified", "installer_evidence_verified",
        "signed_package_chain_verified", "rights_evidence_verified",
        "guarded_local_ai_verified", "security_gates_verified",
        "release_certified",
    ):
        assert report[key] is False


def test_cli_real_single_game_requires_explicit_authorization(
    delivered_first_run, capsys,
):
    (install, archive, save, receipt), pins = delivered_first_run
    args = [
        "consumer-release-evidence", "--mode", "single",
        "--installed", str(install), "--archive", str(archive),
        "--save", str(save), "--receipt", str(receipt),
        "--expected-manifest-sha256", pins["expected_manifest_sha256"],
        "--expected-archive-sha256", pins["expected_archive_sha256"],
        "--expected-save-sha256", pins["expected_save_sha256"],
        "--expected-receipt-sha256", pins["expected_receipt_sha256"],
    ]
    assert run_app_cli(args) == 2
    denied = json.loads(capsys.readouterr().err)
    assert denied["status"] == "blocked"
    assert denied["release_certified"] is False
    assert run_app_cli(args + ["--trusted-local-operator"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "single"
    assert report["release_certified"] is False
    assert report["source_level_evidence"]["action_count"] == 3


def test_real_pinned_cohort_source_level_acceptance_and_holds(
    delivered_games, tmp_path,
):
    jobs, summary, published = delivered_games
    jobfile, job_pin = _file(tmp_path, jobs)
    report = inspect_cohort_consumer_release_hold(
        jobfile, summary, expected_jobs_sha256=job_pin,
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True,
    )
    assert report["mode"] == "cohort"
    evidence = report["source_level_evidence"]
    assert evidence["game_count"] == 2
    assert evidence["private_jobfile_inode_attested"] is True
    assert evidence["all_installed_games_and_private_saves_reexecuted"] is True
    assert report["release_certified"] is False
    assert report["files_published"] == 0


def test_cli_cohort_rejects_cross_mode_inputs_and_requires_pins(
    delivered_games, tmp_path, capsys,
):
    jobs, summary, published = delivered_games
    jobfile, job_pin = _file(tmp_path, jobs)
    args = [
        "consumer-release-evidence", "--mode", "cohort",
        "--jobs-file", str(jobfile), "--summary", str(summary),
        "--expected-jobs-sha256", job_pin,
        "--expected-summary-sha256", published["independent_summary_sha256"],
        "--trusted-local-operator",
    ]
    assert run_app_cli(args + ["--installed", str(jobs[0].install)]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args) == 0
    assert json.loads(capsys.readouterr().out)["release_certified"] is False


@pytest.mark.parametrize("field", [
    "expected_manifest_sha256", "expected_archive_sha256",
    "expected_save_sha256", "expected_receipt_sha256",
])
def test_independent_single_pins_fail_closed(delivered_first_run, field):
    paths, pins = delivered_first_run
    with pytest.raises(ValueError):
        inspect_single_consumer_release_hold(
            *paths, **{**pins, field: "0" * 64},
        )
    with pytest.raises(ConsumerReleaseEvidenceError):
        inspect_single_consumer_release_hold(
            *paths, **{**pins, field: "A" * 64},
        )


@pytest.mark.parametrize("forgery", [
    {"release_certified": True},
    {"native_device_qualified": True},
    {"read_only": False},
    {"release_holds": []},
    {"installed_tree_snapshot_sha256": "z" * 64},
    {"files_published": 1},
    {"source_level_replay_passes": 1},
])
def test_forged_canonical_replay_claims_rejected(
    delivered_first_run, monkeypatch, forgery,
):
    from skeleton.app import consumer_release_evidence as module

    paths, pins = delivered_first_run
    original = module.inspect_consumer_first_run

    def forged(*args, **kwargs):
        return {**original(*args, **kwargs), **forgery}

    monkeypatch.setattr(module, "inspect_consumer_first_run", forged)
    with pytest.raises(ConsumerReleaseEvidenceError):
        inspect_single_consumer_release_hold(*paths, **pins)


def test_untrusted_operator_cannot_trigger_live_replay(delivered_first_run):
    paths, pins = delivered_first_run
    with pytest.raises(PermissionError):
        inspect_single_consumer_release_hold(
            *paths, **{**pins, "authorized": False},
        )

def test_cohort_wrong_jobfile_or_summary_pin_rejected(
    delivered_games, tmp_path,
):
    jobs, summary, published = delivered_games
    jobfile, job_pin = _file(tmp_path, jobs)
    for kwargs in (
        {"expected_jobs_sha256": "0" * 64},
        {"expected_summary_sha256": "0" * 64},
    ):
        with pytest.raises(ValueError):
            inspect_cohort_consumer_release_hold(
                jobfile, summary, authorized=True,
                **{
                    "expected_jobs_sha256": job_pin,
                    "expected_summary_sha256": published["independent_summary_sha256"],
                    **kwargs,
                },
            )


def test_cohort_rejects_non_boolean_source_verification_before_io(
    delivered_games, tmp_path,
):
    jobs, summary, published = delivered_games
    jobfile, job_pin = _file(tmp_path, jobs)
    with pytest.raises(ConsumerReleaseEvidenceError):
        inspect_cohort_consumer_release_hold(
            jobfile, summary, expected_jobs_sha256=job_pin,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True, verify_original_sources="yes",
        )


def test_cohort_cannot_self_certify_device_or_remove_holds(
    delivered_games, tmp_path, monkeypatch,
):
    from skeleton.app import consumer_release_evidence as module

    jobs, summary, published = delivered_games
    jobfile, job_pin = _file(tmp_path, jobs)
    original = module.inspect_pinned_consumer_cohort

    def forged(*args, **kwargs):
        return {
            **original(*args, **kwargs),
            "native_device_qualified": True,
        }

    monkeypatch.setattr(module, "inspect_pinned_consumer_cohort", forged)
    with pytest.raises(ConsumerReleaseEvidenceError):
        inspect_cohort_consumer_release_hold(
            jobfile, summary, expected_jobs_sha256=job_pin,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
