"""Real two-game source -> archive -> install -> move -> save -> replay cohort."""
from __future__ import annotations

from dataclasses import replace
import shutil
from hashlib import sha256
import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.app.cli import run_app_cli
from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, FirstPlayableDeliveryBatchError,
    inspect_first_playable_delivery_batch, publish_first_playable_delivery_batch,
    resume_first_playable_delivery_batch,
)
from skeleton.app.studio_journey import build_first_playable_journey
from skeleton.app.offline_first_playable_delivery import publish_first_playable_delivery


@pytest.fixture(scope="module")
def original_games(tmp_path_factory):
    root = tmp_path_factory.mktemp("original-delivery-cohort")
    games = []
    for index in range(2):
        source = root / f"original-{index}"
        built = build_first_playable_journey(
            GameBuildIntent(
                project_id=f"delivery-cohort-{index}",
                title=f"Original Tidal Village {index}",
                subtitle="Independent local story",
                seed=311 + index, levels=1, width=9, height=9,
                collectibles_per_level=1, hazards_per_level=0,
                starting_health=3,
            ), source, authorized=True, mirror_attempts=64,
        )
        assert built["offline_gameplay_reexecuted"] is True
        games.append((source, sha256((source / "release.json").read_bytes()).hexdigest()))
    return tuple(games)


def jobs_for(games, root):
    return tuple(
        DeliveryJob(
            source=source, archive=root / f"game-{i}.zip",
            install=root / f"installed-{i}", save=root / f"save-{i}.json",
            receipt=root / f"receipt-{i}.json", manifest_sha256=pin,
            moves=("up", "right") if i == 0 else ("down", "left", "up"),
        )
        for i, (source, pin) in enumerate(games)
    )


def pinned(jobs, published):
    return tuple(
        replace(
            job, archive_sha256=record["archive_sha256"],
            save_sha256=record["save_sha256"],
            receipt_sha256=record["independent_receipt_sha256"],
        )
        for job, record in zip(jobs, published["games"], strict=True)
    )


def test_two_original_games_publish_restore_and_independently_reverify(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    assert published["game_count"] == 2
    assert published["all_original_games_replayed"] is True
    assert published["release_certified"] is False
    assert published["native_device_qualified"] is False
    assert published["package_signed"] is False
    assert published["rights_certified"] is False
    for job in jobs:
        assert Path(job.archive).is_file()
        assert Path(job.save).is_file()
        assert Path(job.receipt).is_file()
        assert (Path(job.install) / "index.html").is_file()
    verified = inspect_first_playable_delivery_batch(
        pinned(jobs, published), summary,
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True,
    )
    assert verified["all_live_games_reexecuted"] is True
    assert verified["read_only"] is True
    assert verified["games"] == published["games"]
    assert verified["release_certified"] is False


def test_cross_game_output_collision_fails_before_publication(
    original_games, tmp_path,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(jobs[1], save=jobs[0].receipt)
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_nested_install_and_source_trees_rejected_without_writes(
    original_games, tmp_path,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(jobs[1], install=Path(jobs[0].install) / "nested")
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_summary_inside_any_game_source_is_rejected_before_publication(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, original_games[1][0] / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_missing_operator_authorization_rejects_without_side_effects(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    with pytest.raises(PermissionError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=False,
        )
    assert not Path(jobs[0].archive).exists()


def test_untrusted_or_reused_manifest_pin_rejected_before_publication(
    original_games, tmp_path,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(jobs[1], manifest_sha256=jobs[0].manifest_sha256)
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


@pytest.mark.parametrize("moves", [(), ("wait",), ("up",) * 65, ("up", 1)])
def test_invalid_action_series_rejected_before_first_game(
    original_games, tmp_path, moves,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(jobs[1], moves=moves)
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_cli_rejects_unpinned_inspection_and_untrusted_publication(
    original_games, tmp_path, capsys,
):
    jobs = jobs_for(original_games, tmp_path)
    raw = [
        json.dumps({
            "source": str(job.source), "archive": str(job.archive),
            "install": str(job.install), "save": str(job.save),
            "receipt": str(job.receipt),
            "manifest_sha256": job.manifest_sha256, "moves": list(job.moves),
        })
        for job in jobs
    ]
    args = ["first-playable-batch", "--summary", str(tmp_path / "cohort.json")]
    for item in raw:
        args += ["--job", item]
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args + ["--inspect", "--trusted-local-operator"]) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False
    assert not Path(jobs[0].archive).exists()


def test_cli_full_cohort_publication_and_pinned_reinspection(
    original_games, tmp_path, capsys,
):
    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    def args_for(items):
        args = ["first-playable-batch", "--summary", str(summary),
                "--trusted-local-operator"]
        for job in items:
            value = {
                "source": str(job.source), "archive": str(job.archive),
                "install": str(job.install), "save": str(job.save),
                "receipt": str(job.receipt),
                "manifest_sha256": job.manifest_sha256, "moves": list(job.moves),
            }
            if job.archive_sha256:
                value.update({
                    "archive_sha256": job.archive_sha256,
                    "save_sha256": job.save_sha256,
                    "receipt_sha256": job.receipt_sha256,
                })
            args += ["--job", json.dumps(value)]
        return args
    assert run_app_cli(args_for(jobs)) == 0
    published = json.loads(capsys.readouterr().out)
    assert run_app_cli(args_for(pinned(jobs, published)) + [
        "--inspect", "--expected-summary-sha256",
        published["independent_summary_sha256"],
    ]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["all_live_games_reexecuted"] is True
    assert checked["release_certified"] is False


def test_reinspection_rejects_same_length_different_player_actions(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    altered = list(pinned(jobs, published))
    altered[0] = replace(altered[0], moves=("left", "down"))
    with pytest.raises(FirstPlayableDeliveryBatchError):
        inspect_first_playable_delivery_batch(
            altered, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )


def test_resumable_delivery_requires_independently_pinned_existing_prefix(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    first = jobs[0]
    previous = publish_first_playable_delivery(
        first.source, first.archive, first.install, first.save, first.receipt,
        expected_manifest_sha256=first.manifest_sha256,
        moves=first.moves, authorized=True,
    )
    prefix = replace(
        first, archive_sha256=previous["archive_sha256"],
        save_sha256=previous["save_sha256"],
        receipt_sha256=previous["independent_receipt_sha256"],
    )
    original_receipt = Path(first.receipt).read_bytes()
    resumed = resume_first_playable_delivery_batch(
        (prefix, jobs[1]), tmp_path / "cohort.json", authorized=True,
    )
    assert resumed["previously_published_games"] == 1
    assert resumed["newly_published_games"] == 1
    assert Path(first.receipt).read_bytes() == original_receipt
    verified = inspect_first_playable_delivery_batch(
        pinned(jobs, resumed), tmp_path / "cohort.json",
        expected_summary_sha256=resumed["independent_summary_sha256"],
        authorized=True,
    )
    assert verified["all_live_games_reexecuted"] is True
    assert verified["release_certified"] is False


def test_resume_rejects_unpinned_or_forged_prefix_without_writing_next_game(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    with pytest.raises(FirstPlayableDeliveryBatchError):
        resume_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()
    forged = replace(
        jobs[0], archive_sha256="0" * 64,
        save_sha256="0" * 64, receipt_sha256="0" * 64,
    )
    with pytest.raises((ValueError, OSError)):
        resume_first_playable_delivery_batch(
            (forged, jobs[1]), tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[1].archive).exists()


def test_lexical_dotdot_alias_rejected_before_any_publication(
    original_games, tmp_path,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(
        jobs[1], receipt=tmp_path / "unused" / ".." / "receipt-0.json",
    )
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_delivery_output_ancestor_of_other_output_is_rejected(
    original_games, tmp_path,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(jobs[1], save=Path(jobs[0].archive) / "child.json")
    with pytest.raises(FirstPlayableDeliveryBatchError):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()


def test_job_parser_rejects_duplicate_keys_and_nonfinite_values():
    from skeleton.app.offline_first_playable_batch import _parse_job
    with pytest.raises(FirstPlayableDeliveryBatchError):
        _parse_job('{"source":"a","source":"b"}')
    with pytest.raises(FirstPlayableDeliveryBatchError):
        _parse_job('{"source":NaN}')
    with pytest.raises(FirstPlayableDeliveryBatchError):
        _parse_job('{"source":"a","archive_sha256":42}')


def test_duplicate_project_ids_with_distinct_source_digests_fail_before_writes(
    original_games, tmp_path,
):
    duplicate = tmp_path / "second-source-same-project"
    built = build_first_playable_journey(
        GameBuildIntent(
            project_id="delivery-cohort-0",
            title="Another Original Tidal Village",
            subtitle="Distinct original content with same project identifier",
            seed=991, levels=1, width=9, height=9,
            collectibles_per_level=1, hazards_per_level=0,
            starting_health=3,
        ),
        duplicate, authorized=True, mirror_attempts=64,
    )
    assert built["offline_gameplay_reexecuted"] is True
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[1] = replace(
        jobs[1], source=duplicate,
        manifest_sha256=sha256((duplicate / "release.json").read_bytes()).hexdigest(),
    )
    assert jobs[0].manifest_sha256 != jobs[1].manifest_sha256
    with pytest.raises(
        FirstPlayableDeliveryBatchError,
        match="duplicate original project identity",
    ):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert not Path(jobs[0].archive).exists()
    assert not Path(jobs[1].archive).exists()


@pytest.mark.parametrize("pin", ["", "0" * 63, "A" * 64, "x" * 64])
def test_empty_or_noncanonical_optional_output_pin_rejected_before_writes(
    original_games, tmp_path, pin,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[0] = replace(jobs[0], archive_sha256=pin)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="lowercase SHA-256"):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert all(not Path(job.archive).exists() for job in jobs)


def test_noncanonical_resumed_prefix_pin_fails_before_writing_next_game(
    original_games, tmp_path,
):
    jobs = list(jobs_for(original_games, tmp_path))
    jobs[0] = replace(
        jobs[0], archive_sha256="0" * 64,
        save_sha256="0" * 64, receipt_sha256="",
    )
    with pytest.raises(FirstPlayableDeliveryBatchError, match="lowercase SHA-256"):
        resume_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert all(not Path(job.archive).exists() for job in jobs)


def _copied_original_games(original_games, tmp_path):
    copied = []
    for index, (source, pin) in enumerate(original_games):
        destination = tmp_path / f"copy-source-{index}"
        shutil.copytree(source, destination)
        copied.append((destination, pin))
    return tuple(copied)


def test_publish_rejects_earlier_original_source_mutation_after_later_game(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_batch as batch
    copied = _copied_original_games(original_games, tmp_path)
    jobs = jobs_for(copied, tmp_path)
    original_publish = batch.publish_first_playable_delivery
    completed = 0

    def mutate_after_later_game(*args, **kwargs):
        nonlocal completed
        result = original_publish(*args, **kwargs)
        completed += 1
        if completed == 2:
            (copied[0][0] / "release.json").write_bytes(b'{"tampered":true}')
        return result

    monkeypatch.setattr(batch, "publish_first_playable_delivery",
                        mutate_after_later_game)
    summary = tmp_path / "cohort.json"
    with pytest.raises(ValueError):
        batch.publish_first_playable_delivery_batch(jobs, summary, authorized=True)
    assert completed == 2
    assert Path(jobs[0].archive).exists()
    assert not summary.exists()


def test_resume_rejects_mutated_original_prefix_before_summary_publication(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_batch as batch
    copied = _copied_original_games(original_games, tmp_path)
    jobs = jobs_for(copied, tmp_path)
    first = publish_first_playable_delivery(
        jobs[0].source, jobs[0].archive, jobs[0].install,
        jobs[0].save, jobs[0].receipt,
        expected_manifest_sha256=jobs[0].manifest_sha256,
        moves=jobs[0].moves, authorized=True,
    )
    prefix = replace(
        jobs[0], archive_sha256=first["archive_sha256"],
        save_sha256=first["save_sha256"],
        receipt_sha256=first["independent_receipt_sha256"],
    )
    original_publish = batch.publish_first_playable_delivery

    def mutate_prefix_after_suffix(*args, **kwargs):
        result = original_publish(*args, **kwargs)
        (copied[0][0] / "release.json").write_bytes(b'{"tampered":true}')
        return result

    monkeypatch.setattr(batch, "publish_first_playable_delivery",
                        mutate_prefix_after_suffix)
    summary = tmp_path / "cohort.json"
    with pytest.raises(ValueError):
        batch.resume_first_playable_delivery_batch(
            (prefix, jobs[1]), summary, authorized=True,
        )
    assert Path(jobs[0].receipt).exists()
    assert Path(jobs[1].archive).exists()
    assert not summary.exists()
