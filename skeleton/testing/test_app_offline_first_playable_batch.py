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




def test_batch_preflight_accepts_concrete_pathlib_paths(original_games, tmp_path):
    # Path() creates a PosixPath/WindowsPath, never an exact Path instance.
    # A type(value) in (str, Path) check would reject every real game job.
    from skeleton.app.offline_first_playable_batch import _check_jobs

    jobs = jobs_for(original_games, tmp_path)
    assert all(isinstance(job.source, Path) for job in jobs)
    assert _check_jobs(jobs, tmp_path / "cohort.json", inspect=False) == jobs
    mixed = (replace(jobs[0], source=str(jobs[0].source)), jobs[1])
    assert _check_jobs(mixed, str(tmp_path / "cohort.json"), inspect=False) == mixed


def test_batch_preflight_rejects_untyped_paths_before_publication(
    original_games, tmp_path,
):
    from skeleton.app.offline_first_playable_batch import _check_jobs

    jobs = jobs_for(original_games, tmp_path)
    malformed = (jobs[0], replace(jobs[1], source=object()))
    with pytest.raises(FirstPlayableDeliveryBatchError, match="strings or pathlib Paths"):
        _check_jobs(malformed, tmp_path / "cohort.json", inspect=False)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="summary destination"):
        _check_jobs(jobs, object(), inspect=False)
    assert not Path(jobs[0].archive).exists()
    assert not Path(jobs[1].archive).exists()




def test_cohort_rejects_untyped_canonical_game_digests_and_project_ids():
    from skeleton.app.offline_first_playable_batch import _evidence

    valid = {
        "project_id": "original-game-01",
        "manifest_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
        "save_sha256": "c" * 64,
        "independent_receipt_sha256": "d" * 64,
        "world_digest": "e" * 64,
        "replay_digest": "f" * 64,
        "action_count": 2,
        "offline_gameplay_reexecuted": True,
        "release_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
    }
    assert _evidence(valid)["world_digest"] == "e" * 64
    for key, forged in (
        ("world_digest", "not-a-digest"),
        ("replay_digest", "A" * 64),
        ("world_digest", True),
        ("project_id", "../foreign-game"),
        ("project_id", "game\\ncontrol"),
        ("project_id", "x" * 129),
    ):
        with pytest.raises(FirstPlayableDeliveryBatchError):
            _evidence({**valid, key: forged})


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


def test_cohort_stops_before_second_publication_when_first_source_changes(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_batch as batch

    copied = _copied_original_games(original_games, tmp_path)
    jobs = jobs_for(copied, tmp_path)
    original_publish = batch.publish_first_playable_delivery
    calls = 0

    def mutate_after_first_game(*args, **kwargs):
        nonlocal calls
        result = original_publish(*args, **kwargs)
        calls += 1
        if calls == 1:
            (copied[0][0] / "release.json").write_bytes(b'{"tampered":true}')
        return result

    monkeypatch.setattr(batch, "publish_first_playable_delivery",
                        mutate_after_first_game)
    summary = tmp_path / "cohort.json"
    with pytest.raises(ValueError):
        batch.publish_first_playable_delivery_batch(jobs, summary, authorized=True)
    assert calls == 1
    assert Path(jobs[0].archive).exists()  # preserve published evidence
    assert not Path(jobs[1].archive).exists()  # no unnecessary second write
    assert not summary.exists()


def test_cohort_stops_before_second_publication_when_first_receipt_changes(
    original_games, tmp_path, monkeypatch,
):
    from skeleton.app import offline_first_playable_batch as batch

    jobs = jobs_for(original_games, tmp_path)
    original_publish = batch.publish_first_playable_delivery
    calls = 0

    def mutate_receipt_after_first_game(*args, **kwargs):
        nonlocal calls
        result = original_publish(*args, **kwargs)
        calls += 1
        if calls == 1:
            Path(jobs[0].receipt).write_bytes(b'{"untrusted":true}')
        return result

    monkeypatch.setattr(batch, "publish_first_playable_delivery",
                        mutate_receipt_after_first_game)
    summary = tmp_path / "cohort.json"
    with pytest.raises(ValueError):
        batch.publish_first_playable_delivery_batch(jobs, summary, authorized=True)
    assert calls == 1
    assert Path(jobs[0].archive).exists()
    assert not Path(jobs[1].archive).exists()
    assert not summary.exists()


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("manifest_sha256", "F" * 64),
        ("archive_sha256", "short"),
        ("save_sha256", 0),
        ("independent_receipt_sha256", None),
        ("project_id", ""),
        ("world_digest", None),
        ("replay_digest", ""),
        ("world_digest", "world-digest"),
        ("replay_digest", "replay-digest"),
        ("action_count", True),
        ("action_count", 65),
    ],
)
def test_cohort_record_rejects_untyped_canonical_delivery_contract(
    field, bad_value,
):
    from skeleton.app.offline_first_playable_batch import _record

    result = {
        "project_id": "original-game",
        "manifest_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
        "save_sha256": "c" * 64,
        "independent_receipt_sha256": "d" * 64,
        "world_digest": "e" * 64,
        "replay_digest": "f" * 64,
        "action_count": 2,
        "offline_gameplay_reexecuted": True,
        "release_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
    }
    result[field] = bad_value
    with pytest.raises(FirstPlayableDeliveryBatchError):
        _record(result, ("up", "right"))


def test_cohort_record_rejects_replay_count_mismatch_and_unsupported_moves():
    from skeleton.app.offline_first_playable_batch import _record

    result = {
        "project_id": "original-game",
        "manifest_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
        "save_sha256": "c" * 64,
        "independent_receipt_sha256": "d" * 64,
        "world_digest": "e" * 64,
        "replay_digest": "f" * 64,
        "action_count": 2,
        "offline_gameplay_reexecuted": True,
        "release_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
    }
    assert _record(result, ("up", "right"))["action_count"] == 2
    with pytest.raises(FirstPlayableDeliveryBatchError):
        _record(result, ("up",))
    with pytest.raises(FirstPlayableDeliveryBatchError):
        _record(result, ("up", "teleport"))


def test_read_only_cohort_inspection_rejects_same_byte_summary_inode_swap(
    original_games, tmp_path, monkeypatch,
):
    import os
    from skeleton.app import offline_first_playable_batch as batch

    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    original_read = batch.read_private_game_save
    reads = 0

    def replace_after_first_summary_read(path, *args, **kwargs):
        nonlocal reads
        raw = original_read(path, *args, **kwargs)
        if Path(path) == summary:
            reads += 1
            if reads == 1:
                replacement = tmp_path / "same-byte-replacement"
                replacement.write_bytes(raw)
                replacement.chmod(0o600)
                os.replace(replacement, summary)
        return raw

    monkeypatch.setattr(batch, "read_private_game_save",
                        replace_after_first_summary_read)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="inode"):
        batch.inspect_first_playable_delivery_batch(
            pinned(jobs, published), summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
    assert reads >= 1
    assert summary.exists()  # read-only inspector never deletes evidence


def test_opt_in_original_source_provenance_inspection_detects_post_delivery_change(
    original_games, tmp_path,
):
    copied = _copied_original_games(original_games, tmp_path)
    jobs = jobs_for(copied, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    independent = pinned(jobs, published)
    verified = inspect_first_playable_delivery_batch(
        independent, summary,
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True, verify_original_sources=True,
    )
    assert verified["original_sources_reverified"] is True
    assert verified["release_certified"] is False

    (copied[0][0] / "release.json").write_bytes(b'{"tampered":true}')
    with pytest.raises(ValueError):
        inspect_first_playable_delivery_batch(
            independent, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True, verify_original_sources=True,
        )
    # Offline delivery remains independently verifiable after the authoring
    # workspace changes, but must never claim to have reverified that source.
    archived = inspect_first_playable_delivery_batch(
        independent, summary,
        expected_summary_sha256=published["independent_summary_sha256"],
        authorized=True,
    )
    assert archived["original_sources_reverified"] is False
    assert archived["release_certified"] is False


def test_original_source_inspection_flag_rejects_non_boolean(
    original_games, tmp_path,
):
    jobs = jobs_for(original_games, tmp_path)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="boolean"):
        inspect_first_playable_delivery_batch(
            jobs, tmp_path / "missing-summary",
            expected_summary_sha256="a" * 64,
            authorized=True, verify_original_sources="yes",
        )


def test_batch_cli_deeply_nested_job_fails_closed_before_any_write(
    tmp_path, capsys,
):
    malformed = "[" * 1500 + "0" + "]" * 1500
    assert run_app_cli([
        "first-playable-batch", "--job", malformed, "--job", malformed,
        "--summary", str(tmp_path / "cohort.json"),
        "--trusted-local-operator",
    ]) == 2
    result = json.loads(capsys.readouterr().err)
    assert result["status"] == "blocked"
    assert result["release_certified"] is False
    assert not (tmp_path / "cohort.json").exists()


@pytest.mark.parametrize("plane", ("archive", "install", "save", "receipt"))
def test_cohort_replay_rejects_same_byte_earlier_game_inode_swap(
    original_games, tmp_path, monkeypatch, plane,
):
    """A later game's replay must not hide replacement of an earlier output."""
    import os
    from skeleton.app import offline_first_playable_batch as module

    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    checked = pinned(jobs, published)
    original_inspector = module.inspect_first_playable_delivery
    calls = 0
    target = Path(getattr(jobs[0], plane))

    def replace_earlier_output_during_second_replay(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            replacement = tmp_path / f"replacement-{plane}"
            if plane == "install":
                shutil.copytree(target, replacement)
                old = tmp_path / "old-installed-source"
                os.rename(target, old)
                os.rename(replacement, target)
            else:
                shutil.copy2(target, replacement)
                os.replace(replacement, target)
        return original_inspector(*args, **kwargs)

    monkeypatch.setattr(
        module, "inspect_first_playable_delivery",
        replace_earlier_output_during_second_replay,
    )
    with pytest.raises(
        FirstPlayableDeliveryBatchError, match="custody changed",
    ):
        inspect_first_playable_delivery_batch(
            checked, summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
    assert calls == 2
    assert summary.is_file()
    assert published["release_certified"] is False


def test_cohort_custody_snapshot_rejects_unreadable_later_member(
    original_games, tmp_path,
):
    """The entire cohort must be admissible before replaying the first game."""
    from skeleton.app.offline_first_playable_batch import _delivered_custody

    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    first = _delivered_custody(jobs)
    assert len(first) == 2
    assert all(len(identities) == 4 for identities in first)
    Path(jobs[1].receipt).unlink()
    with pytest.raises((OSError, ValueError)):
        inspect_first_playable_delivery_batch(
            pinned(jobs, published), summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
    assert Path(jobs[0].receipt).exists()


def test_source_cohort_detects_first_root_swap_during_second_source_replay(
    original_games, tmp_path, monkeypatch,
):
    """Later source verification cannot hide same-byte earlier-root replacement."""
    import os
    from skeleton.app import offline_first_playable_batch as module
    from skeleton.ai.game_builder.dual_runtime_verify import verify_exported_package

    copied = []
    for index, (source, manifest_pin) in enumerate(original_games):
        new_source = tmp_path / f"source-copy-{index}"
        shutil.copytree(source, new_source)
        copied.append((new_source, manifest_pin))
    jobs = jobs_for(tuple(copied), tmp_path)
    identities = tuple(module._source_identity(job.source) for job in jobs)
    admissions = tuple(
        verify_exported_package(
            job.source, expected_manifest_sha256=job.manifest_sha256,
            authorized=True,
        )
        for job in jobs
    )
    first = Path(jobs[0].source)
    replacement = tmp_path / "identical-source"
    shutil.copytree(first, replacement)
    original_verify = module.verify_exported_package
    calls = 0

    def swap_first_after_second_verification(*args, **kwargs):
        nonlocal calls
        result = original_verify(*args, **kwargs)
        calls += 1
        if calls == 2:
            old = tmp_path / "previous-source"
            os.rename(first, old)
            os.rename(replacement, first)
        return result

    monkeypatch.setattr(module, "verify_exported_package",
                        swap_first_after_second_verification)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="source root changed"):
        module._reverify_original_sources(jobs, admissions, identities)
    assert calls == 2
    assert all(not Path(job.archive).exists() for job in jobs)


def test_publish_rejects_source_root_swap_inside_first_preflight(
    original_games, tmp_path, monkeypatch,
):
    """Pin root inode before preflight, not after the verifier has returned."""
    import os
    from skeleton.app import offline_first_playable_batch as module

    cloned = []
    for index, (source, manifest_pin) in enumerate(original_games):
        path = tmp_path / f"cloned-game-{index}"
        shutil.copytree(source, path)
        cloned.append((path, manifest_pin))
    jobs = jobs_for(tuple(cloned), tmp_path)
    first = Path(jobs[0].source)
    replacement = tmp_path / "same-byte-game"
    shutil.copytree(first, replacement)
    original_preflight = module._preflight
    calls = 0

    def swap_after_successful_preflight(*args, **kwargs):
        nonlocal calls
        admitted = original_preflight(*args, **kwargs)
        calls += 1
        if calls == 1:
            old = tmp_path / "old-game-root"
            os.rename(first, old)
            os.rename(replacement, first)
        return admitted

    monkeypatch.setattr(module, "_preflight", swap_after_successful_preflight)
    with pytest.raises(FirstPlayableDeliveryBatchError, match="during preflight"):
        publish_first_playable_delivery_batch(
            jobs, tmp_path / "cohort.json", authorized=True,
        )
    assert calls == 1
    assert all(not Path(job.archive).exists() for job in jobs)
    assert not (tmp_path / "cohort.json").exists()


def test_second_cohort_replay_detects_late_in_place_installed_file_edit(
    original_games, tmp_path, monkeypatch,
):
    """A root-inode snapshot alone cannot detect edits to an existing file."""
    from skeleton.app import offline_first_playable_batch as module

    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    original_inspector = module.inspect_first_playable_delivery
    target = Path(jobs[0].install) / "index.html"
    original = target.read_bytes()
    assert len(original) > 1
    before_root = module._source_identity(jobs[0].install)
    calls = 0

    def mutate_first_game_after_second_game_replay(*args, **kwargs):
        nonlocal calls
        result = original_inspector(*args, **kwargs)
        calls += 1
        if calls == 2:
            target.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            # Editing a preexisting file does not change the parent directory.
            assert module._source_identity(jobs[0].install) == before_root
        return result

    monkeypatch.setattr(
        module, "inspect_first_playable_delivery",
        mutate_first_game_after_second_game_replay,
    )
    # The per-pass delivered-custody barrier (content digests, not just the
    # root inode) must catch the same-inode edit made during game 2's replay
    # before any later pass is trusted.
    with pytest.raises((OSError, ValueError),
                       match="digest mismatch|custody changed"):
        inspect_first_playable_delivery_batch(
            pinned(jobs, published), summary,
            expected_summary_sha256=published["independent_summary_sha256"],
            authorized=True,
        )
    assert calls >= 2
    assert target.read_bytes() != original
    assert published["release_certified"] is False


def test_pinned_summary_record_schema_rejected_before_live_replay(
    original_games, tmp_path,
):
    """Even an independently pinned JSON blob is not a typed game receipt."""
    from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
    from skeleton.app.offline_first_playable_batch import _validated_stored_records

    base_jobs = jobs_for(original_games, tmp_path)
    jobs = tuple(
        replace(
            job, archive_sha256=f"{index + 1:064x}",
            save_sha256=f"{index + 3:064x}",
            receipt_sha256=f"{index + 5:064x}",
        )
        for index, job in enumerate(base_jobs)
    )
    records = [
        {
            "project_id": f"original-test-{index}",
            "manifest_sha256": job.manifest_sha256,
            "archive_sha256": job.archive_sha256,
            "save_sha256": job.save_sha256,
            "independent_receipt_sha256": job.receipt_sha256,
            "world_digest": f"{index + 7:064x}",
            "replay_digest": f"{index + 9:064x}",
            "action_count": len(job.moves),
            "moves_sha256": sha256(
                _canonical_bytes(list(job.moves))
            ).hexdigest(),
        }
        for index, job in enumerate(jobs)
    ]
    assert _validated_stored_records({"games": records}, jobs) == records
    malformed = (
        (0, "project_id", {"unexpected": "object"}),
        (0, "project_id", "../foreign"),
        (0, "world_digest", "0" * 63),
        (0, "action_count", True),
        (0, "action_count", len(jobs[0].moves) + 1),
        (0, "manifest_sha256", "f" * 64),
        (0, "moves_sha256", "f" * 64),
        (1, "independent_receipt_sha256", records[0]["independent_receipt_sha256"]),
    )
    for index, key, value in malformed:
        changed = [dict(record) for record in records]
        changed[index][key] = value
        with pytest.raises(FirstPlayableDeliveryBatchError):
            _validated_stored_records({"games": changed}, jobs)
    for variant in (
        [dict(records[0])],
        [dict(records[0]), "not a record"],
        [dict(records[0]), {**records[1], "extra": 1}],
        [dict(records[1]), dict(records[0])],
    ):
        with pytest.raises(FirstPlayableDeliveryBatchError):
            _validated_stored_records({"games": variant}, jobs)


def test_independently_pinned_malformed_summary_fails_before_game_replay(
    original_games, tmp_path, monkeypatch,
):
    """A valid independent SHA cannot launder hostile summary JSON as evidence."""
    from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
    from skeleton.app import offline_first_playable_batch as module
    from skeleton.app.private_game_save import publish_private_game_save

    jobs = jobs_for(original_games, tmp_path)
    summary = tmp_path / "cohort.json"
    published = publish_first_playable_delivery_batch(
        jobs, summary, authorized=True,
    )
    stored = json.loads(summary.read_bytes())
    stored["games"][0]["project_id"] = {"not": "a string"}
    forged = tmp_path / "forged-summary.json"
    forged_pin = publish_private_game_save(
        _canonical_bytes(stored), forged,
        protected_roots=tuple(
            root for job in jobs for root in (job.source, job.install)
        ),
        authorized=True,
    )
    def must_not_replay(*args, **kwargs):
        raise AssertionError("malformed summary reached live game replay")
    monkeypatch.setattr(module, "inspect_first_playable_delivery", must_not_replay)
    with pytest.raises(
        FirstPlayableDeliveryBatchError, match="original project identity",
    ):
        inspect_first_playable_delivery_batch(
            pinned(jobs, published), forged,
            expected_summary_sha256=forged_pin, authorized=True,
        )
    assert forged.exists()
    assert all(Path(job.save).exists() for job in jobs)
