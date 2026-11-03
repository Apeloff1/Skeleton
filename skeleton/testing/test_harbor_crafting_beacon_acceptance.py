"""Original beacon acceptance proves real replayed victory, not structure alone."""
from __future__ import annotations

from copy import deepcopy
import subprocess

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, canonical, decode, digest
from skeleton.game.gameplay.harbor_crafting_beacon_acceptance import (
    accept_beacon_play, verify_beacon_acceptance,
)
from skeleton.game.gameplay.harbor_crafting_beacon_package import (
    build_beacon_package, play_beacon_package,
)
from skeleton.testing.test_harbor_crafting_beacons import (
    CLI, source_board, winning_actions,
)


def winning_play():
    source, board = source_board()
    return play_beacon_package(
        build_beacon_package("lantern-beacon-rescue", source, board),
        winning_actions(), require_rescue=True,
    )


def test_full_source_to_canonical_victory_to_acceptance():
    play = winning_play()
    certificate = accept_beacon_play(play)
    result = verify_beacon_acceptance(play, decode(canonical(certificate)))
    assert result["verified"] and result["rescued"]
    assert result["score"] == 80 - 22 + 20
    assert certificate["proof"]["ordered_signals"] == ["canal_light", "dock_light"]
    assert certificate["proof"]["ending"] == "beacon"
    assert certificate["proof"]["canonical_tip"] == play["report"]["bundle"]["terminal_digest"]


def test_unearned_or_resealed_forged_acceptance_is_rejected():
    play = winning_play()
    certificate = accept_beacon_play(play)
    for key, value in (
        ("rescue_score", 999999), ("rescued", False), ("ending", "safe_harbor"),
        ("ordered_signals", ["dock_light", "canal_light"]),
    ):
        forged = deepcopy(certificate)
        forged["proof"][key] = value
        forged["acceptance_digest"] = digest({
            k: v for k, v in forged.items() if k != "acceptance_digest"
        })
        with pytest.raises(HarborError, match="replay"):
            verify_beacon_acceptance(play, forged)
    source, board = source_board()
    partial = play_beacon_package(
        build_beacon_package("lantern-beacon-rescue", source, board),
        winning_actions()[:-1],
    )
    with pytest.raises(HarborError, match="not earned"):
        accept_beacon_play(partial)
    with pytest.raises(HarborError):
        verify_beacon_acceptance(partial, certificate)


def test_acceptance_cli_round_trip_and_rejection(tmp_path):
    play = winning_play()
    play_path = tmp_path / "play.json"
    play_path.write_bytes(canonical(play))
    command = CLI + ["accept", "--play", str(play_path)]
    created = subprocess.run(command, capture_output=True, check=False)
    assert created.returncode == 0, created.stderr.decode()
    certificate = decode(created.stdout)
    cert_path = tmp_path / "acceptance.json"
    cert_path.write_bytes(canonical(certificate))
    verified = subprocess.run(
        CLI + ["verify-accept", "--play", str(play_path),
               "--acceptance", str(cert_path)],
        capture_output=True, check=False,
    )
    assert verified.returncode == 0, verified.stderr.decode()
    assert decode(verified.stdout)["verified"]
    cert_path.write_bytes(b'{"schema":"fake"}')
    rejected = subprocess.run(
        CLI + ["verify-accept", "--play", str(play_path),
               "--acceptance", str(cert_path)],
        capture_output=True, check=False,
    )
    assert rejected.returncode == 2


def test_independent_beacons_accept_actual_earned_signal_order():
    source, board = source_board()
    board = deepcopy(board)
    board["beacons"][1]["requires"] = []
    demo = winning_actions()
    # The dock signal is earned first; then the player returns to the canal.
    actions = (
        demo[:12]
        + [{"op": "move", "direction": "east"}] * 4
        + [{"op": "repair", "beacon": "dock_light"},
           {"op": "signal", "beacon": "dock_light"}]
        + [{"op": "move", "direction": "west"}] * 4
        + [{"op": "repair", "beacon": "canal_light"},
           {"op": "signal", "beacon": "canal_light"}]
        + [{"op": "move", "direction": "east"}] * 4
        + [{"op": "deliver"}, {"op": "rescue"}]
    )
    play = play_beacon_package(
        build_beacon_package("lantern-alternate-beacons", source, board),
        actions, require_rescue=True,
    )
    certificate = accept_beacon_play(play)
    assert certificate["proof"]["ordered_signals"] == ["dock_light", "canal_light"]
    assert verify_beacon_acceptance(play, certificate)["verified"]
