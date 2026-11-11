"""Read-only nofollow quarantine triage for interrupted playable delivery."""
from __future__ import annotations

from dataclasses import replace
import shutil
import os
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




def _pinned_prefix_for_triage(original_games, tmp_path):
    jobs = jobs_for(original_games, tmp_path)
    first = jobs[0]
    published = publish_first_playable_delivery(
        first.source, first.archive, first.install, first.save, first.receipt,
        expected_manifest_sha256=first.manifest_sha256,
        moves=first.moves, authorized=True,
    )
    return (
        replace(first, archive_sha256=published["archive_sha256"],
                save_sha256=published["save_sha256"],
                receipt_sha256=published["independent_receipt_sha256"]),
        jobs[1],
    )


def test_resume_triage_rejects_late_same_byte_prefix_inode_swap(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_batch_triage as module

    jobs = _pinned_prefix_for_triage(original_games, tmp_path)
    original_preflight = module._preflight
    swapped = False

    def swap_after_suffix_preflight(*args, **kwargs):
        nonlocal swapped
        result = original_preflight(*args, **kwargs)
        if not swapped:
            target = Path(jobs[0].archive)
            replacement = tmp_path / "same-bytes-replacement.zip"
            replacement.write_bytes(target.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, target)
            swapped = True
        return result

    monkeypatch.setattr(module, "_preflight", swap_after_suffix_preflight)
    result = module.triage_first_playable_delivery_batch(
        jobs, tmp_path / "cohort.json", authorized=True,
    )
    assert swapped is True
    assert result["resume_eligible_with_independent_pins"] is False
    assert result["resume_source_preflight_verified"] is False
    assert result["release_certified"] is False


def test_resume_triage_rejects_suffix_output_created_after_preflight(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_batch_triage as module

    jobs = _pinned_prefix_for_triage(original_games, tmp_path)
    original_preflight = module._preflight

    def publish_untrusted_suffix_after_preflight(*args, **kwargs):
        result = original_preflight(*args, **kwargs)
        Path(jobs[1].archive).write_bytes(b"untrusted late artifact")
        return result

    monkeypatch.setattr(module, "_preflight", publish_untrusted_suffix_after_preflight)
    result = module.triage_first_playable_delivery_batch(
        jobs, tmp_path / "cohort.json", authorized=True,
    )
    assert result["resume_eligible_with_independent_pins"] is False
    assert result["resume_source_preflight_verified"] is False
    assert Path(jobs[1].archive).read_bytes() == b"untrusted late artifact"
    assert result["release_certified"] is False


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
    assert result["resume_source_preflight_verified"] is True
    assert result["resume_destinations_reserved"] is False
    assert result["jobs"][0]["state"] == "independently_pinned_replay_verified"
    assert result["jobs"][1]["state"] == "missing_unpublished"
    assert Path(first.receipt).read_bytes() == receipt_before
    assert not Path(jobs[1].archive).exists()


def test_unpinned_partial_publication_requires_quarantine(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    Path(jobs[0].archive).write_bytes(b"untrusted")
    # Model a genuine interrupted publication: the publisher writes owner-only
    # files, so a group/world-readable leftover would be (correctly) "unsafe".
    Path(jobs[0].archive).chmod(0o600)
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


def test_parent_replacement_during_missing_entry_triage_is_unsafe(
    original_games, tmp_path, monkeypatch,
):
    """Missing-name diagnosis cannot trust a replaced directory pathname."""
    from skeleton.app import offline_first_playable_batch_triage as module

    parent = tmp_path / "owned-archive-parent"
    parent.mkdir()
    moved = tmp_path / "old-archive-parent"
    jobs = list(jobs_for(original_games, tmp_path))
    archive = parent / "original-game.zip"
    jobs[0] = replace(jobs[0], archive=archive)
    original_stat = module.os.stat
    swapped = False

    def replace_after_descriptor_open(path, *args, **kwargs):
        nonlocal swapped
        if (not swapped and path == archive.name
                and kwargs.get("dir_fd") is not None):
            swapped = True
            parent.rename(moved)
            parent.mkdir()
            raise FileNotFoundError(path)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "stat", replace_after_descriptor_open)
    result = triage_first_playable_delivery_batch(
        jobs, tmp_path / "cohort.json", authorized=True,
    )
    assert swapped is True
    assert result["jobs"][0]["state"] == "unsafe_custody_quarantine"
    assert result["resume_eligible_with_independent_pins"] is False
    assert result["read_only"] is True
    assert result["release_certified"] is False
    assert not archive.exists()


def test_missing_suffix_with_tampered_original_source_is_not_resume_eligible(
    original_games, tmp_path,
):
    copied = []
    for index, (source, pin) in enumerate(original_games):
        destination = tmp_path / f"original-copy-{index}"
        shutil.copytree(source, destination)
        copied.append((destination, pin))
    jobs = jobs_for(tuple(copied), tmp_path)
    first = jobs[0]
    published = publish_first_playable_delivery(
        first.source, first.archive, first.install, first.save, first.receipt,
        expected_manifest_sha256=first.manifest_sha256,
        moves=first.moves, authorized=True,
    )
    prefix = replace(
        first, archive_sha256=published["archive_sha256"],
        save_sha256=published["save_sha256"],
        receipt_sha256=published["independent_receipt_sha256"],
    )
    (copied[1][0] / "release.json").write_bytes(b'{"tampered":true}')
    summary = tmp_path / "cohort.json"
    result = triage_first_playable_delivery_batch(
        (prefix, jobs[1]), summary, authorized=True,
    )
    assert result["verified_prefix_count"] == 1
    assert result["jobs"][1]["state"] == "missing_unpublished"
    assert result["resume_eligible_with_independent_pins"] is False
    assert result["resume_source_preflight_verified"] is False
    assert result["resume_destinations_reserved"] is False
    assert result["read_only"] is True
    assert result["release_certified"] is False
    assert not summary.exists()
    assert not Path(jobs[1].archive).exists()
