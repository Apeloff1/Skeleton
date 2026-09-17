from __future__ import annotations

import json

import pytest

from skeleton.game.ai_policy import AIPolicyError, next_state, run_policy
from skeleton.game.era_bind import EraBindError, bind_era
from skeleton.game.harbor import Harbor, HarborError
from skeleton.game.mass import MassError, clip_mass, observe_mass, trajectory
from skeleton.game.mechanics import AIBehaviorSpec
from skeleton.game.pack import PackError, validate_pack
from skeleton.game.session import run_session


def test_ai_policy_is_deterministic() -> None:
    spec = AIBehaviorSpec(
        entity_type="stalker",
        behaviors=("patrol", "chase"),
        aggression_level=0.7,
        intelligence_level=0.5,
    )
    left = run_policy(spec, seed=8847291, ticks=16)
    right = run_policy(spec, seed=8847291, ticks=16)
    assert left == right
    assert {frame["state"] for frame in left} <= {"idle", "patrol", "chase", "retreat", "extract"}
    assert next_state(spec, seed=1, tick=0, hp_ratio=0.05, heat_ratio=0.1) == "retreat"
    with pytest.raises(AIPolicyError):
        run_policy(spec, seed=1, ticks=0)


def test_harbor_weights_and_reversible_bag() -> None:
    harbor = Harbor(weights={"scrap": 0.5, "parts": 0.5})
    harbor.put("scrap", 3).take("scrap", 3)
    assert "scrap" not in harbor.bag
    with pytest.raises(HarborError, match="sum"):
        Harbor(weights={"scrap": 0.2, "parts": 0.2})
    with pytest.raises(HarborError, match="forbidden"):
        Harbor(weights={"coin": 1.0})
    with pytest.raises(HarborError, match="underflow"):
        Harbor().take("scrap")


def test_mass_clip_and_stamped_ten_fail() -> None:
    assert clip_mass(1.0, 2.0) == pytest.approx(1.1)
    path = trajectory(1.0, 20)
    assert path[0] == 1.0
    assert path[-1] / path[0] <= 1.1**20 + 1e-6
    with pytest.raises(MassError, match="stamped"):
        observe_mass(g=10.0, g0=10.0, citation="#807")
    card = observe_mass(g=1.05, g0=1.0, citation="#807")
    assert card["stored_prose"] == 0
    assert card["law"] == "prior_times_1_1"


def test_era_bind_and_pack_fail_closed() -> None:
    card = bind_era()
    assert card["stored_prose"] == 0
    assert card["era"] == "extraction_now"
    with pytest.raises(EraBindError):
        bind_era(era="cyberpunk-2077")
    with pytest.raises(EraBindError):
        bind_era(url="http://example.com")
    ok = validate_pack(
        {
            "combat": {"style": "real_time", "include_magic": False},
            "economy": {"currencies": ["scrap"]},
            "progression": {"style": "linear", "max_level": 8},
        }
    )
    assert ok["combat_style"] == "real_time"
    with pytest.raises(PackError, match="missing"):
        validate_pack({"combat": {"style": "turn_based"}})


def test_session_digest_stable_and_cli(capsys: pytest.CaptureFixture[str]) -> None:
    inputs = [{"t": 0, "verb": "attack"}, {"t": 1, "verb": "wait"}]
    left = run_session(seed=7, inputs=inputs, forges=4)
    right = run_session(seed=7, inputs=inputs, forges=4)
    assert left["digest"] == right["digest"]
    assert left["replay_digest"] == right["replay_digest"]
    assert left["harbor"]["sum"] == pytest.approx(1.0)
    assert left["reference"]["stored_prose"] == 0
    other = run_session(seed=8, inputs=inputs, forges=4)
    assert other["digest"] != left["digest"]

    from skeleton.__main__ import main

    assert main(["session", "--seed", "7"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
    assert len(printed["digest"]) == 64
