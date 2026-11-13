"""Legal action hints are exact source-bound, not speculative suggestions."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, digest, load_source,
)
from skeleton.game.gameplay.harbor_crafting_convoy_league import build_league
from skeleton.game.gameplay.harbor_crafting_convoy_league_solver import solve_league
from skeleton.game.gameplay.harbor_crafting_convoy_league_guidance import (
    build_league_guidance, verify_league_guidance,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"
CLI = [sys.executable, "-m", "skeleton.game.gameplay.harbor_crafting_cli"]


def source_league():
    return (
        load_source(FIXTURES / "harbor_lantern_quay.json"),
        decode((FIXTURES / "harbor_lantern_quay_convoy_league.json").read_bytes()),
    )


def test_guidance_is_exact_transition_and_terminal_is_empty():
    source, league = source_league()
    initial = build_league(source, league, [])
    guidance = build_league_guidance(initial)
    assert verify_league_guidance(decode(canonical(guidance)))["verified"]
    assert guidance["next_round"] == "canal_relief"
    assert guidance["legal"]
    for row in guidance["legal"]:
        from skeleton.game.gameplay.harbor_crafting_convoy_league import resume_league
        advanced = resume_league(
            initial, [row["action"]], expected_digest=initial["save_digest"],
        )
        assert advanced["save_digest"] == row["next_save_digest"]
    finished = solve_league(source, league)["save"]
    assert build_league_guidance(finished)["legal"] == []


def test_guidance_forgery_and_cli_replay(tmp_path):
    source, league = source_league()
    initial = build_league(source, league, [])
    guidance = build_league_guidance(initial)
    forged = deepcopy(guidance)
    forged["legal"] = []
    forged["guidance_digest"] = digest({
        key: value for key, value in forged.items() if key != "guidance_digest"
    })
    with pytest.raises(HarborError, match="replay"):
        verify_league_guidance(forged)
    path = tmp_path / "save.json"
    path.write_bytes(canonical(initial))
    proc = subprocess.run(CLI + ["league-hint", "--league-save", str(path)],
                          capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode()
    assert decode(proc.stdout) == guidance
    hint = tmp_path / "hint.json"
    hint.write_bytes(proc.stdout)
    verify = subprocess.run(CLI + ["league-verify-hint", "--league-hint", str(hint)],
                            capture_output=True, check=False)
    assert verify.returncode == 0, verify.stderr.decode()
    assert decode(verify.stdout)["legal_count"] == len(guidance["legal"])
