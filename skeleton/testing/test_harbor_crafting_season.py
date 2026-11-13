"""End-to-end source -> playable rounds -> CAS save -> export -> replay -> ranking."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_season import (
    append_season, build_season, season_board, validate_season,
    verify_season_board, verify_season_record,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def authored():
    world = load_source(ROOT / "harbor_lantern_quay.json")
    first = decode((ROOT / "harbor_lantern_quay_time_trial.json").read_bytes())
    second = deepcopy(first)
    second["deadline"] = 33
    second["medals"] = {"gold": 19, "silver": 25, "bronze": 33}
    season = {
        "schema": "skeleton.game.harbor.season.v1", "source_id": world["id"],
        "points": {"gold": 10, "silver": 7, "bronze": 4, "finish": 2},
        "rounds": [{"id": "lantern_sprint", "course": first},
                   {"id": "night_shift", "course": second}],
    }
    return world, season


def games(world):
    first = export_bundle(world, demo_actions(), require_win=True)
    second = export_bundle(world, [{"op": "wait"}] + demo_actions(), require_win=True)
    return first, second


def test_source_to_multi_round_earned_championship_and_portable_replay():
    world, season = authored()
    first, second = games(world)
    root = build_season(world, season, [])
    assert root["next_round"] == 0 and not root["complete"]
    checkpoint = append_season(root, first, expected_record_digest=root["record_digest"])
    assert checkpoint["next_round"] == 1 and checkpoint["total_points"] == 10
    final = append_season(checkpoint, second, expected_record_digest=checkpoint["record_digest"])
    assert final["complete"] and final["next_round"] == 2
    assert final["total_points"] == 20  # 18 and 19 ticks earn gold on both courses
    assert verify_season_record(decode(canonical(final)))["total_points"] == 20
    assert canonical(final) == canonical(build_season(world, season, [first, second]))


def test_stale_lease_and_completed_season_refuse_append():
    world, season = authored()
    first, second = games(world)
    root = build_season(world, season, [])
    with pytest.raises(HarborError, match="stale"):
        append_season(root, first, expected_record_digest="0" * 64)
    final = build_season(world, season, [first, second])
    with pytest.raises(HarborError, match="already complete"):
        append_season(final, first, expected_record_digest=final["record_digest"])


@pytest.mark.parametrize("mutation", [
    lambda r: r.update({"total_points": 999}),
    lambda r: r["results"][0].update({"points": 100}),
    lambda r: r["results"][1].update({"id": "lantern_sprint"}),
    lambda r: r["results"][0]["report"].update({"medal": "bronze"}),
    lambda r: r["results"][0]["report"]["bundle"]["state"].update({"coins": 1000}),
    lambda r: r["results"].reverse(),
])
def test_resealed_score_or_gameplay_forgery_is_rejected(mutation):
    world, season = authored()
    record = build_season(world, season, list(games(world)))
    mutation(record)
    record["record_digest"] = digest({k: v for k, v in record.items() if k != "record_digest"})
    with pytest.raises(HarborError):
        verify_season_record(record)


def test_source_and_authoring_fail_closed():
    world, season = authored()
    invalid = deepcopy(season)
    invalid["rounds"][1]["id"] = invalid["rounds"][0]["id"]
    with pytest.raises(HarborError, match="duplicate season round"):
        validate_season(invalid, world)
    invalid = deepcopy(season)
    invalid["rounds"][1]["course"] = deepcopy(invalid["rounds"][0]["course"])
    with pytest.raises(HarborError, match="duplicate season course"):
        validate_season(invalid, world)
    invalid = deepcopy(season)
    invalid["points"]["gold"] = True
    with pytest.raises(HarborError, match="invalid season points"):
        validate_season(invalid, world)
    foreign = deepcopy(world)
    foreign["initial_coins"] += 1
    with pytest.raises(HarborError, match="source mismatch"):
        build_season(world, season, [export_bundle(foreign, demo_actions(), require_win=True)])


def test_missing_win_or_duplicate_replay_is_rejected():
    world, season = authored()
    first, _ = games(world)
    with pytest.raises(HarborError, match="victory not earned"):
        build_season(world, season, [export_bundle(world, demo_actions()[:3])])
    with pytest.raises(HarborError, match="duplicate season game replay"):
        build_season(world, season, [first, first])


def test_deterministic_standings_replay_and_tampering():
    world, season = authored()
    first, second = games(world)
    root = build_season(world, season, [])
    partial = build_season(world, season, [first])
    complete = build_season(world, season, [first, second])
    board = season_board([partial, complete, root])
    assert board["ranking"][0]["complete"] is True
    assert [entry["rounds"] for entry in board["ranking"]] == [2, 1, 0]
    assert verify_season_board(decode(canonical(board))) == board["ranking"]
    with pytest.raises(HarborError, match="duplicate season board"):
        season_board([complete, complete])
    forged = deepcopy(board)
    forged["ranking"][0]["points"] = 100
    forged["board_digest"] = digest({k: v for k, v in forged.items() if k != "board_digest"})
    with pytest.raises(HarborError, match="replay mismatch"):
        verify_season_board(forged)


def test_cli_source_to_checkpoint_append_verify_and_board(tmp_path):
    world, season = authored()
    first, second = games(world)
    season_path = tmp_path / "season.json"
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    season_path.write_bytes(canonical(season))
    first_path.write_bytes(canonical(first))
    second_path.write_bytes(canonical(second))
    def call(*args):
        proc = subprocess.run(CLI + list(args), capture_output=True, check=False)
        assert proc.returncode == 0, proc.stderr.decode()
        return decode(proc.stdout)
    root = call("season-init", "--season", str(season_path))
    save_path = tmp_path / "record.json"
    save_path.write_bytes(canonical(root))
    partial = call("season-append", "--season-record", str(save_path),
                   "--bundle", str(first_path),
                   "--expected-season-digest", root["record_digest"])
    save_path.write_bytes(canonical(partial))
    final = call("season-append", "--season-record", str(save_path),
                 "--bundle", str(second_path),
                 "--expected-season-digest", partial["record_digest"])
    save_path.write_bytes(canonical(final))
    assert call("season-verify", "--season-record", str(save_path))["complete"] is True
    records_path = tmp_path / "records.json"
    records_path.write_bytes(canonical([partial, final]))
    board = call("season-board", "--season-records", str(records_path))
    board_path = tmp_path / "board.json"
    board_path.write_bytes(canonical(board))
    assert call("season-board-verify", "--season-board", str(board_path))["ranking"][0]["rounds"] == 2
    stale = subprocess.run(CLI + [
        "season-append", "--season-record", str(save_path), "--bundle", str(first_path),
        "--expected-season-digest", root["record_digest"],
    ], capture_output=True, check=False)
    assert stale.returncode == 2
    assert b"stale" in stale.stderr


def test_fixture_driven_season_next_and_terminal_play(tmp_path):
    world = load_source(ROOT / "harbor_lantern_quay.json")
    season = decode((ROOT / "harbor_lantern_quay_season.json").read_bytes())
    root = build_season(world, season, [])
    from skeleton.game.gameplay.harbor_crafting_season import next_season_round
    ready = next_season_round(root)
    assert ready["status"] == "ready"
    assert ready["round"]["id"] == "lantern_sprint"
    record_path = tmp_path / "season-record.json"
    record_path.write_bytes(canonical(root))
    proc = subprocess.run(CLI + [
        "season-next", "--season-record", str(record_path),
    ], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode()
    assert decode(proc.stdout)["round"] == ready["round"]
    from skeleton.game.gameplay.harbor_crafting_ui import scripted_demo_commands
    live = subprocess.run(CLI + [
        "season-live", "--season-record", str(record_path),
    ], input=scripted_demo_commands().encode(), capture_output=True, check=False)
    assert live.returncode == 0, live.stderr.decode() + live.stdout.decode()[-800:]
    assert b"TRIAL finished gold" in live.stdout
    assert b"CHECKPOINT " in live.stdout
    first, second = games(world)
    with pytest.raises(HarborError, match="finish not earned"):
        build_season(world, season, [first, second])
    shelter_actions = [{"op": "wait"}] + demo_actions()
    shelter_actions[-1] = {"op": "choose", "choice": "shelter"}
    shelter = export_bundle(world, shelter_actions, require_win=True)
    complete = build_season(world, season, [first, shelter])
    assert complete["results"][1]["report"]["bundle"]["state"]["ending"] == "safe_harbor"
    assert next_season_round(complete)["status"] == "complete"
    record_path.write_bytes(canonical(complete))
    rejected = subprocess.run(CLI + [
        "season-live", "--season-record", str(record_path),
    ], capture_output=True, check=False)
    assert rejected.returncode == 2
    assert b"already complete" in rejected.stderr
