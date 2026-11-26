"""Catalog cards behind the seam gate. No model is called."""
from __future__ import annotations

import pytest

from skeleton.local_ai.artifact_plane import process as artifact
from skeleton.local_ai.capability_index import CARDS, export
from skeleton.local_ai.census_preview import CENSUS, process as census
from skeleton.local_ai.chief_of_staff import process as chief
from skeleton.local_ai.clipped_mass import CLIP, process as clipped
from skeleton.local_ai.dna_genos import PAIRS, emit
from skeleton.local_ai.economy_harbor import WEIGHTS, process as economy
from skeleton.local_ai.frontier_gates import GATES, process as gates
from skeleton.local_ai.gameforge_workflow import process as workflow
from skeleton.local_ai.gap_filler import GapFiller
from skeleton.local_ai.hive_chronicle import ROOTS, gossip
from skeleton.local_ai.lora_contact import attach
from skeleton.local_ai.mobile_bank_card import process as mobile
from skeleton.local_ai.security_ace import process as ace
from skeleton.local_ai.skill_creator import SKILLS, create
from skeleton.local_ai.specdec_local import process as steer
from skeleton.local_ai.specdec_steer import SpecDecSteer
from skeleton.local_ai.squash_ledger import process as ledger
from skeleton.local_ai.swarm_turn import process as swarm


def test_cards_publish_their_pins_and_refuse_secrets():
    secret = {"note": "api_key=nope"}
    assert gates({})["gates"] == GATES
    assert gates({"gate": "secret_scan"})["gate"] == "secret_scan"
    assert gates({"gate": "other"})["error"] == "unknown gate"
    assert gates(secret) == {"ok": False, "error": "payload refused", "card": "frontier_gates"}
    assert "api_key" not in str(gates(secret))

    cycle = swarm({"verb": "sleep"})
    assert cycle["next"] == "extract"
    assert swarm({"verb": "dance"})["error"] == "unknown verb"

    walked = workflow({"step": "export"})
    assert walked["index"] == 6
    assert walked["next"] == "vision"
    assert census({"count": CENSUS})["census"] == CENSUS
    assert census({"count": 1})["error"] == "census is pinned"
    assert clipped({"growth": CLIP})["growth"] == CLIP
    assert clipped({"growth": CLIP + 0.01})["error"] == "growth exceeds the clip"
    assert clipped({"growth": True})["ok"] is False
    assert chief({"action": "push"})["error"] == "duty is dispatch only"
    assert artifact({"path": "notes/readme.md"})["path"] == "notes/readme.md"
    assert artifact({"path": "../engine.dll"})["error"] == "binary stays off the plane"
    assert economy({})["sum"] == pytest.approx(1.0)
    assert economy({})["weights"] == WEIGHTS
    assert economy({"weights": {"bag": 1}})["error"] == "weights are fixed"
    assert mobile({"sse": True})["error"] == "mobile flag stays dark"
    assert ledger({"remote": True})["error"] == "ledger stays local"
    assert steer({"h": 2, "u": 5})["steered"] == pytest.approx(2.5)
    assert steer({"alpha": 0.9})["error"] == "alpha is pinned"
    assert ace({"path": "notes/readme.md"})["ok"] is True
    assert ace({"path": "secrets.env"})["error"] == "path is forbidden"


def test_bounded_registers_reject_overflow_and_duplicates():
    SKILLS.clear()
    create("KettleWatch")
    create("KettleWatch")
    assert SKILLS == ["KettleWatch"]
    with pytest.raises(ValueError):
        create("api_key=nope")
    with pytest.raises(ValueError):
        create("1bad")

    PAIRS.clear()
    emit({"left": "a", "right": "t"})
    emit({"left": "a", "right": "t"})
    assert PAIRS == [{"left": "a", "right": "t"}]
    with pytest.raises(ValueError):
        emit({"left": "a", "extra": "no"})

    ROOTS.clear()
    gossip("local-0")
    gossip("local-0")
    assert ROOTS == ["local-0"]
    with pytest.raises(ValueError):
        gossip("../escape")
    gossip("a" * 64)
    assert ROOTS[-1] == "a" * 64

    CARDS.clear()
    export("Vision", "House")
    export("Vision", "House")
    assert CARDS == [{"name": "Vision", "owner": "House"}]
    with pytest.raises(ValueError):
        export("Vision", "bad owner")

    card = attach("HouseCopy", rank=4, alpha=8)
    assert card == {"name": "HouseCopy", "rank": 4, "alpha": 8.0, "house": "dialect"}
    with pytest.raises(ValueError):
        attach("HouseCopy", rank=0)

    steered = SpecDecSteer().steer([1.0, 2.0], [0.5, 0.0], 0.1)
    assert steered == pytest.approx([1.05, 2.0])
    with pytest.raises(ValueError):
        SpecDecSteer().steer([1.0], [0.5, 0.0])
    assert SpecDecSteer().verify("", "target") is False


def test_gap_filler_registers_the_cards():
    names = set(GapFiller().list())
    expected = {
        "artifact_plane",
        "census_preview",
        "chief_of_staff",
        "clipped_mass",
        "frontier_gates",
        "gameforge_workflow",
        "swarm_turn",
        "economy_harbor",
        "security_ace",
        "skill_creator",
        "dna_genos",
        "hive_chronicle",
        "lora_contact",
        "specdec_steer",
    }
    assert expected <= names
    record = GapFiller().call("swarm_turn", {"verb": "heat"})
    assert record["ok"] is True
    assert record["next"] == "sleep"
