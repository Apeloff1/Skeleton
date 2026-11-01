"""Real two-game source -> archive -> install -> move -> save -> replay cohort."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.app.cli import run_app_cli
from skeleton.app.offline_first_playable_batch import (
    DeliveryJob, FirstPlayableDeliveryBatchError,
    inspect_first_playable_delivery_batch, publish_first_playable_delivery_batch,
)
from skeleton.app.studio_journey import build_first_playable_journey


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
