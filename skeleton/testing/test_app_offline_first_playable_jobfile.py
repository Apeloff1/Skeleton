"""Real original-game cohort integration through a private pinned job file."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_first_playable_jobfile import (
    SCHEMA, FirstPlayableJobFileError, execute_pinned_jobfile,
    read_pinned_jobs,
)
from skeleton.testing.test_app_offline_first_playable_batch import (
    jobs_for, original_games, pinned,
)


def _payload(jobs):
    return {
        "schema": SCHEMA,
        "jobs": [
            {
                "source": str(job.source), "archive": str(job.archive),
                "install": str(job.install), "save": str(job.save),
                "receipt": str(job.receipt),
                "manifest_sha256": job.manifest_sha256,
                "moves": list(job.moves),
                **({
                    "archive_sha256": job.archive_sha256,
                    "save_sha256": job.save_sha256,
                    "receipt_sha256": job.receipt_sha256,
                } if job.archive_sha256 is not None else {}),
            }
            for job in jobs
        ],
    }


def _file(root, jobs, name="jobs.json"):
    path = root / name
    path.write_text(json.dumps(_payload(jobs), sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return path, sha256(path.read_bytes()).hexdigest()


def test_cli_pinned_jobfile_publish_and_replay_inspect(original_games, tmp_path, capsys):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"
    base = ["first-playable-jobfile", "--jobs-file", str(manifest),
            "--expected-jobs-sha256", pin, "--summary", str(summary),
            "--trusted-local-operator"]
    assert run_app_cli(base + ["--mode", "publish"]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["game_count"] == 2
    assert published["input_manifest_sha256"] == pin
    assert published["input_manifest_unchanged"] is True
    assert published["release_certified"] is False
    assert (tmp_path / "installed-0" / "index.html").is_file()
    assert (tmp_path / "installed-1" / "index.html").is_file()
    inspected_file, inspected_pin = _file(
        tmp_path, pinned(jobs, published), "pinned-jobs.json",
    )
    inspect_args = [
        "first-playable-jobfile", "--jobs-file", str(inspected_file),
        "--expected-jobs-sha256", inspected_pin, "--summary", str(summary),
        "--mode", "inspect", "--expected-summary-sha256",
        published["independent_summary_sha256"], "--trusted-local-operator",
    ]
    assert run_app_cli(inspect_args) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["all_live_games_reexecuted"] is True
    assert inspected["read_only"] is True
    assert inspected["original_sources_reverified"] is False
    assert inspected["release_certified"] is False
    assert run_app_cli(inspect_args + ["--verify-original-sources"]) == 0
    source_bound = json.loads(capsys.readouterr().out)
    assert source_bound["original_sources_reverified"] is True
    assert source_bound["all_live_games_reexecuted"] is True
    assert source_bound["input_manifest_unchanged"] is True
    assert source_bound["release_certified"] is False


def test_triage_from_private_file_does_not_create_outputs(original_games, tmp_path):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"
    result = execute_pinned_jobfile(
        manifest, expected_jobs_sha256=pin, summary=summary,
        mode="triage", authorized=True,
    )
    assert result["summary_state"] == "missing"
    assert result["read_only"] is True
    assert result["input_manifest_unchanged"] is True
    assert not Path(jobs[0].archive).exists()
    assert not summary.exists()


@pytest.mark.parametrize("mutation", [
    "wrong_pin", "symlink", "hardlink", "world_writable",
    "duplicate_key", "nan", "missing_schema",
])
def test_untrusted_jobfile_rejected_before_publication(
    original_games, tmp_path, mutation,
):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    if mutation == "wrong_pin":
        pin = "0" * 64
    elif mutation == "symlink":
        alias = tmp_path / "alias.json"
        alias.symlink_to(manifest)
        manifest = alias
    elif mutation == "hardlink":
        alias = tmp_path / "alias.json"
        os.link(manifest, alias)
        manifest = alias
    elif mutation == "world_writable":
        manifest.chmod(0o666)
    elif mutation == "duplicate_key":
        manifest.write_text('{"schema":"x","schema":"y","jobs":[]}')
        pin = sha256(manifest.read_bytes()).hexdigest()
    elif mutation == "nan":
        manifest.write_text('{"schema":NaN,"jobs":[]}')
        pin = sha256(manifest.read_bytes()).hexdigest()
    elif mutation == "missing_schema":
        manifest.write_text('{"jobs":[]}')
        pin = sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises((FirstPlayableJobFileError, OSError, ValueError)):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin,
            summary=tmp_path / "cohort.json", mode="publish", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_jobfile_must_not_overlap_output_or_source(original_games, tmp_path):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    with pytest.raises(FirstPlayableJobFileError):
        read_pinned_jobs(
            manifest, expected_sha256=pin, summary=manifest,
            mode="publish", authorized=True,
        )
    with pytest.raises(FirstPlayableJobFileError):
        read_pinned_jobs(
            manifest, expected_sha256=pin, summary=tmp_path / "cohort.json",
            mode="unsupported", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_jobfile_mutation_during_delivery_fails_closed(
    original_games, tmp_path, monkeypatch,
):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    from skeleton.app import offline_first_playable_jobfile as module

    def fake_publish(*args, **kwargs):
        manifest.write_text(json.dumps(_payload(jobs)) + " ", encoding="utf-8")
        return {"release_certified": False}

    monkeypatch.setattr(module, "publish_first_playable_delivery_batch", fake_publish)
    with pytest.raises(FirstPlayableJobFileError):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin,
            summary=tmp_path / "cohort.json", mode="publish", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_untrusted_authorization_and_wrong_mode_pin_rejected(original_games, tmp_path):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    with pytest.raises(PermissionError):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin,
            summary=tmp_path / "cohort.json", mode="publish", authorized=False,
        )
    with pytest.raises(FirstPlayableJobFileError):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin,
            summary=tmp_path / "cohort.json", mode="inspect", authorized=True,
        )
    with pytest.raises(FirstPlayableJobFileError):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin,
            summary=tmp_path / "cohort.json", mode="publish",
            expected_summary_sha256="0" * 64, authorized=True,
        )


def test_preflight_replays_both_sources_without_reserving_outputs(
    original_games, tmp_path, capsys,
):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"
    args = [
        "first-playable-jobfile", "--jobs-file", str(manifest),
        "--expected-jobs-sha256", pin, "--summary", str(summary),
        "--mode", "preflight", "--trusted-local-operator",
    ]
    assert run_app_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["game_count"] == 2
    assert result["all_original_sources_replayed"] is True
    assert result["source_root_inodes_stable"] is True
    assert result["destinations_reserved"] is False
    assert result["outputs_published"] is False
    assert result["read_only"] is True
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert not summary.exists()
    for job in jobs:
        assert not Path(job.archive).exists()
        assert not Path(job.install).exists()
        assert not Path(job.save).exists()


def test_preflight_rejects_occupied_later_output_without_partial_write(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    occupied = Path(jobs[1].receipt)
    occupied.write_bytes(b"operator-owned")
    occupied.chmod(0o600)
    with pytest.raises((OSError, ValueError)):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin,
            summary=tmp_path / "cohort.json", mode="preflight",
            authorized=True,
        )
    assert occupied.read_bytes() == b"operator-owned"
    assert not Path(jobs[0].archive).exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_preflight_rejects_same_byte_original_source_root_replacement(
    original_games, tmp_path, monkeypatch,
):
    """A later game cannot hide an earlier game's source-root replacement."""
    import shutil
    from skeleton.app import offline_first_playable_jobfile as module

    jobs = jobs_for(original_games, tmp_path)
    original_preflight = module._preflight
    calls = 0
    source = Path(jobs[0].source)
    replacement = tmp_path / "copied-source-root"
    old = tmp_path / "old-source-root"
    shutil.copytree(source, replacement)

    def swap_first_root_during_second_game(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            os.rename(source, old)
            os.rename(replacement, source)
        return original_preflight(*args, **kwargs)

    monkeypatch.setattr(module, "_preflight", swap_first_root_during_second_game)
    with pytest.raises(FirstPlayableJobFileError, match="root changed"):
        module.preflight_pinned_cohort(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert calls == 2
    assert not (tmp_path / "cohort.json").exists()
    assert all(not Path(job.archive).exists() for job in jobs)


def test_inspection_with_original_source_replay_rejects_missing_authoring_tree(
    original_games, tmp_path, capsys,
):
    """Archived installed games stay inspectable, but cannot claim source custody."""
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"
    published = execute_pinned_jobfile(
        manifest, expected_jobs_sha256=pin, summary=summary,
        mode="publish", authorized=True,
    )
    inspected_file, inspected_pin = _file(
        tmp_path, pinned(jobs, published), "inspect-pinned-jobs.json",
    )
    first_source = Path(jobs[0].source)
    first_source.rename(tmp_path / "archived-original-source")
    archived = execute_pinned_jobfile(
        inspected_file, expected_jobs_sha256=inspected_pin,
        summary=summary, mode="inspect",
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True,
    )
    assert archived["all_live_games_reexecuted"] is True
    assert archived["original_sources_reverified"] is False
    with pytest.raises((OSError, ValueError)):
        execute_pinned_jobfile(
            inspected_file, expected_jobs_sha256=inspected_pin,
            summary=summary, mode="inspect",
            expected_summary_sha256=published["independent_summary_sha256"],
            verify_original_sources=True, authorized=True,
        )
    assert summary.exists()
    assert Path(jobs[0].install).exists()


def test_original_source_replay_option_rejected_for_mutating_modes(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"
    with pytest.raises(FirstPlayableJobFileError, match="inspection-only"):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin, summary=summary,
            mode="publish", verify_original_sources=True, authorized=True,
        )
    with pytest.raises(FirstPlayableJobFileError, match="inspection-only"):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin, summary=summary,
            mode="preflight", verify_original_sources=1, authorized=True,
        )
    assert not summary.exists()
    assert all(not Path(job.archive).exists() for job in jobs)


def test_failed_publication_still_rechecks_jobfile_custody(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_jobfile as module
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"

    def fail_after_input_mutation(*args, **kwargs):
        manifest.write_bytes(manifest.read_bytes() + b" ")
        raise RuntimeError("simulated interrupted canonical publisher")

    monkeypatch.setattr(module, "publish_first_playable_delivery_batch",
                        fail_after_input_mutation)
    with pytest.raises(FirstPlayableJobFileError):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin, summary=summary,
            mode="publish", authorized=True,
        )
    assert not summary.exists()


def test_failed_publication_with_stable_input_preserves_original_failure(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_jobfile as module
    jobs = jobs_for(original_games, tmp_path)
    manifest, pin = _file(tmp_path, jobs)
    summary = tmp_path / "cohort.json"

    def fail_without_mutation(*args, **kwargs):
        raise RuntimeError("simulated canonical publisher fault")

    monkeypatch.setattr(module, "publish_first_playable_delivery_batch",
                        fail_without_mutation)
    with pytest.raises(RuntimeError, match="canonical publisher fault"):
        execute_pinned_jobfile(
            manifest, expected_jobs_sha256=pin, summary=summary,
            mode="publish", authorized=True,
        )
    assert sha256(manifest.read_bytes()).hexdigest() == pin
    assert not summary.exists()


def test_deeply_nested_untrusted_jobfile_fails_as_typed_rejection(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    manifest, _ = _file(tmp_path, jobs)
    # Well below the byte budget but beyond the JSON parser recursion budget.
    manifest.write_bytes(b"[" * 1500 + b"0" + b"]" * 1500)
    pin = sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(FirstPlayableJobFileError, match="invalid strict UTF-8"):
        read_pinned_jobs(
            manifest, expected_sha256=pin, summary=tmp_path / "cohort.json",
            mode="publish", authorized=True,
        )
    assert all(not Path(job.archive).exists() for job in jobs)
