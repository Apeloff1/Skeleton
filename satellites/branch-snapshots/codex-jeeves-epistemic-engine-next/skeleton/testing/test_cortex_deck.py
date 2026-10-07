"""Command-deck smoke — laws, refs, speak-like path, dodeca, genos card."""
from __future__ import annotations

from urllib.parse import urlparse

from skeleton.cortex.antiplag import guard, score
from skeleton.cortex.deck import CommandDeck
from skeleton.cortex.dodeca import FACES, face_card
from skeleton.cortex.laws import LAWS, LawError, check
from skeleton.cortex.refs import lookup, refer
from skeleton.organism.quality_state import latest_repair, load_quality


class _Engine:
    G = 1.0
    pulses = 0
    epsilon = 0.0


class _Dummy:
    genos_engine = _Engine()

    def speaking_name(self) -> str:
        return "neo"

    def think(self, stimulus, context=None):
        class _A:
            text = stimulus

        class _T:
            used_own = False
            amalgam = _A()

            def to_dict(self):
                return {"amalgam": stimulus, "used_own": False}

        return _T()

    def improve(self, stimulus, rounds=6):
        ref = lookup(stimulus)
        if not ref:
            return {"improved": 0, "reason": "no-reference"}
        return {
            "kind": "improve",
            "improved": 1,
            "title": ref["title"],
            "era": ref["era"],
            "citation": ref["citation"],
            "stored_prose": 0,
            "G0": 1.0,
            "G": 1.37,
            "ratio": 1.37,
            "target": 10.0,
            "rounds": rounds,
        }

    def ascend(self, stimulus, rounds=6):
        card = self.improve(stimulus, rounds=rounds)
        if card.get("improved"):
            card = {**card, "kind": "ascend"}
        return card

    def genos(self, stimulus):
        self.genos_engine.pulses += 1
        self.genos_engine.G *= 1.11
        return {"ok": 1, "G": round(self.genos_engine.G, 6), "pulse": self.genos_engine.pulses}

    def status(self):
        return {"dummy": 1}


def test_twelve_laws_and_faces():
    assert len(LAWS) == 6
    assert len(FACES) == 12
    assert "cite-do-not-copy" in LAWS


def test_lookup_elden_ring_is_pointer():
    ref = lookup("like Elden Ring")
    assert ref is not None
    assert ref["title"] == "Elden Ring"
    assert ref["appid"] == 1245620
    assert ref["stored_prose"] == 0
    steam_host = (urlparse(ref["url"]).hostname or "").lower()
    assert steam_host == "steampowered.com" or steam_host.endswith(".steampowered.com")
    assert ref["license"].startswith("LicenseRef-Steam")


def test_refer_records_no_prose():
    out = refer("hollow knight")
    assert out["hit"] == 1
    assert out["ref"]["stored_prose"] == 0
    assert out["provenance"]["stored_prose"] == 0
    assert "sha256" in out["provenance"]


def test_guard_rejects_title_copy():
    try:
        guard("elden ring elden ring elden ring elden ring", "Elden Ring")
    except LawError as exc:
        assert exc.law == "cite-do-not-copy"
    else:
        s = score("plan tensor ttk hp dps stagger posture", "Elden Ring")
        assert s["copy"] is False


def test_check_rejects_prose_keys():
    try:
        check({"extract": "the lands between is a vast"})
        raise AssertionError("expected LawError")
    except LawError as exc:
        assert exc.law == "no-third-party-prose"


def test_deck_speak_like_ascends():
    deck = CommandDeck(_Dummy())
    card = deck.speak("like Elden Ring")
    assert card["hit"] == 1
    assert card["stored_prose"] == 0
    assert card["improve"]["improved"] == 1
    assert card["improve"]["kind"] == "ascend"
    assert "soulslike" in card["amalgam"]
    assert deck.last_ref["title"] == "Elden Ring"
    assert len(deck.traces) == 1


def test_deck_speak_without_ref_stays_legal():
    deck = CommandDeck(_Dummy())
    card = deck.speak("plan tensor ttk lattice")
    assert card["hit"] == 0
    assert card["improve"] is None
    assert card["law"] == "ok"


def test_deck_plan_attaches_quality_contract_and_persists(tmp_path):
    deck = CommandDeck(_Dummy(), root=tmp_path)
    card = deck.plan("like Elden Ring")
    assert card["quality"]["accepted"] is True
    assert card["quality"]["quality"]["metadata"]["kind"] == "plan"
    assert card["quality_stats"]["runs"] == 1
    assert card["era"] == "soulslike"
    rows = load_quality(root=tmp_path)
    assert rows and rows[-1]["surface"] == "plan"


def test_deck_plan_can_repair_once(tmp_path):
    deck = CommandDeck(_Dummy(), root=tmp_path)
    card = deck.plan("", repair=True)
    assert "quality" in card
    assert latest_repair(root=tmp_path, surface="plan")


def test_deck_walk_and_pick():
    deck = CommandDeck(_Dummy())
    w = deck.walk(3)
    assert w["seed"] == 8847291
    assert w["face"] in FACES
    assert len(w["walk"]) == 3
    p = deck.pick(7)
    assert p["position"] == 7
    assert p["face"] == FACES[7]


def test_deck_genos_steps():
    deck = CommandDeck(_Dummy())
    a = deck.genos()
    b = deck.genos()
    assert a["G"] < b["G"]
    assert b["pulse"] == 2


def test_face_card_shape():
    card = face_card(_Dummy())
    assert card["of"] == 12
    assert card["house"] == "dodecahedron"
    assert set(card["faces"]).issubset(set(FACES))
