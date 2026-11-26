"""GF-P1-42: drift and conflict across simultaneous authoring passes."""

from __future__ import annotations

import pytest

from skeleton.forge.authoring_drift import (
    AuthoringDriftError,
    AuthoringGate,
    AuthoringPatch,
    AuthoringPass,
    capture_pass,
    live_canon_digest,
    live_save_revision,
    project_patch,
    review_authoring_passes,
)
from skeleton.forge.game_frontier_event_authority import (
    CanonRules,
    EnvironmentalLedger,
    EventAuthorityError,
    QuestSpec,
    SaveState,
)
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger,
    RPGEventAction,
    RPGEventPage,
)

_KEY = b"era-authority-key-0001"


def _canon() -> CanonRules:
    return CanonRules.build(
        (
            QuestSpec("lantern-watch", ("notice", "sheltered"), era_engines=frozenset({"meadow"})),
            QuestSpec("well-path", ("mark", "descend"), era_engines=frozenset({"meadow"})),
        ),
        immutable_flags=frozenset({"king_dead"}),
    )


def _ledger() -> EnvironmentalLedger:
    return EnvironmentalLedger(SaveState("meadow"), _canon(), keys={"warden": _KEY})


def _patch(patch_id: str, quests: dict | None = None, flags: dict | None = None) -> AuthoringPatch:
    return AuthoringPatch(patch_id, quests or {}, flags or {})


def test_simultaneous_passes_capture_the_live_canon_digest_and_save_revision():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    first = gate.submit(_patch("pass-a", {"lantern-watch": 1}, {"wet": True}))
    second = gate.submit(_patch("pass-b", {"well-path": 0}, {"wind": False}))
    assert first.base_canon_digest == live_canon_digest(ledger)
    assert second.base_canon_digest == first.base_canon_digest
    assert first.base_save_revision == live_save_revision(ledger) == 0
    assert second.base_save_revision == 0
    assert first.patch.quest_stages["lantern-watch"] == 1
    assert second.patch.flags["wind"] is False
    assert ledger.state.revision == 0
    assert ledger.state.quest_stage == {}
    assert ledger.state.flags == {}


def test_canon_digest_drift_cannot_promote():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    drifted = AuthoringPass("0" * 64, ledger.state.revision, _patch("pass-a", {"lantern-watch": 1}))
    gate.hold(drifted)
    report = gate.review()
    assert report.verdicts[0].drifted is True
    assert report.verdicts[0].drift_reasons == ("canon_digest",)
    assert report.verdicts[0].can_promote is False
    with pytest.raises(AuthoringDriftError, match="drifted canon digest"):
        gate.promote("pass-a", reviewer_id="Mara Quill")
    assert ledger.state.revision == 0
    assert ledger.state.quest_stage == {}


def test_save_revision_drift_cannot_promote():
    ledger = _ledger()
    patch = _patch("pass-a", {"lantern-watch": 0})
    drifted = AuthoringPass(live_canon_digest(ledger), 4, patch)
    report = review_authoring_passes(ledger, (drifted,))
    assert report.verdicts[0].drift_reasons == ("save_revision",)
    assert report.verdicts[0].can_promote is False
    gate = AuthoringGate(ledger)
    gate.hold(drifted)
    with pytest.raises(AuthoringDriftError, match="drifted save revision"):
        gate.promote("pass-a", reviewer_id="Mara Quill")
    assert live_save_revision(ledger) == 0


def test_live_save_movement_drifts_an_open_pass():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"well-path": 1}))
    ledger.state = SaveState("meadow", revision=1)
    report = gate.review()
    assert report.verdicts[0].drift_reasons == ("canon_digest", "save_revision")
    with pytest.raises(AuthoringDriftError, match="drifted"):
        gate.promote("pass-a", reviewer_id="Mara Quill")
    assert ledger.state.revision == 1
    assert ledger.state.quest_stage == {}


def test_quest_conflict_names_the_quest_and_promotes_neither():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 0}))
    gate.submit(_patch("pass-b", {"lantern-watch": 1}))
    report = gate.review()
    assert report.contested_quests == ("lantern-watch",)
    assert report.contested_keys == ("quest:lantern-watch",)
    assert all(verdict.can_promote is False for verdict in report.verdicts)
    for patch_id in ("pass-a", "pass-b"):
        with pytest.raises(AuthoringDriftError, match="contested keys") as raised:
            gate.promote(patch_id, reviewer_id="Mara Quill")
        assert raised.value.contested_keys == ("quest:lantern-watch",)
    assert ledger.state.revision == 0
    assert "lantern-watch" not in ledger.state.quest_stage


def test_flag_conflict_names_the_flag_and_promotes_neither():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", flags={"wet": True}))
    gate.submit(_patch("pass-b", flags={"wet": False}))
    report = gate.review()
    assert report.contested_flags == ("wet",)
    assert report.contested_keys == ("flag:wet",)
    for patch_id in ("pass-a", "pass-b"):
        with pytest.raises(AuthoringDriftError, match="flag:wet") as raised:
            gate.promote(patch_id, reviewer_id="Mara Quill")
        assert raised.value.contested_keys == ("flag:wet",)
    assert ledger.state.revision == 0
    assert ledger.state.flags == {}


def test_mixed_conflict_names_every_contested_key():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 0}, {"wet": True, "wind": True}))
    gate.submit(_patch("pass-b", {"lantern-watch": 1}, {"wet": False}))
    report = gate.review()
    assert report.contested_keys == ("flag:wet", "quest:lantern-watch")
    assert report.contested_quests == ("lantern-watch",)
    assert report.contested_flags == ("wet",)
    assert "wind" not in report.contested_flags
    with pytest.raises(AuthoringDriftError, match="contested keys") as raised:
        gate.promote("pass-a", reviewer_id="Mara Quill")
    assert raised.value.contested_keys == ("flag:wet", "quest:lantern-watch")
    assert ledger.state.revision == 0


def test_same_value_is_not_a_conflict():
    ledger = _ledger()
    passes = (
        capture_pass(ledger, _patch("pass-a", {"lantern-watch": 1}, {"wet": True})),
        capture_pass(ledger, _patch("pass-b", {"lantern-watch": 1}, {"wet": True})),
    )
    report = review_authoring_passes(ledger, passes)
    assert report.contested_keys == ()
    assert all(verdict.can_promote is True for verdict in report.verdicts)


def test_drifted_pass_does_not_contest_a_fresh_pass():
    ledger = _ledger()
    fresh = capture_pass(ledger, _patch("fresh", {"lantern-watch": 0}))
    stale = AuthoringPass("0" * 64, 3, _patch("stale", {"lantern-watch": 1}))
    report = review_authoring_passes(ledger, (fresh, stale))
    by_id = {verdict.patch_id: verdict for verdict in report.verdicts}
    assert report.contested_keys == ()
    assert by_id["fresh"].can_promote is True
    assert by_id["stale"].drifted is True
    assert by_id["stale"].can_promote is False


def test_blank_and_anonymous_reviewers_are_rejected():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 0}, {"wet": True}))
    for reviewer_id in ("", "   ", "anonymous", "Anonymous", "ANONYMOUS", " anonymous "):
        with pytest.raises(AuthoringDriftError, match="reviewer"):
            gate.promote("pass-a", reviewer_id=reviewer_id)
    assert ledger.state.revision == 0
    assert ledger.state.quest_stage == {}
    assert ledger.state.flags == {}
    promoted = gate.promote("pass-a", reviewer_id="Mara Quill")
    assert promoted.revision == 1
    assert promoted.quest_stage["lantern-watch"] == 0
    assert promoted.flags["wet"] is True


def test_immutable_flag_edit_is_rejected_and_a_later_clean_pass_can_promote():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("sealed", flags={"king_dead": False}))
    report = gate.review()
    assert report.verdicts[0].immutable_flags == ("king_dead",)
    assert report.verdicts[0].can_promote is False
    with pytest.raises(AuthoringDriftError, match="immutable flag king_dead"):
        gate.promote("sealed", reviewer_id="Mara Quill")
    assert ledger.state.revision == 0
    assert "king_dead" not in ledger.state.flags
    state = ledger.state
    with pytest.raises(AuthoringDriftError, match="immutable flag king_dead"):
        project_patch(state, ledger.canon, _patch("sealed", flags={"king_dead": True}))
    assert ledger.state is state
    gate.submit(_patch("open-path", {"well-path": 0}))
    promoted = gate.promote("open-path", reviewer_id="Mara Quill")
    assert promoted.revision == 1
    assert promoted.quest_stage["well-path"] == 0
    assert "king_dead" not in promoted.flags


def test_project_patch_returns_the_next_save_without_applying_it():
    ledger = _ledger()
    state = ledger.state
    digest = live_canon_digest(ledger)
    projected = project_patch(
        state,
        ledger.canon,
        _patch("pass-a", {"lantern-watch": 1}, {"wet": True}),
    )
    assert ledger.state is state
    assert live_save_revision(ledger) == 0
    assert live_canon_digest(ledger) == digest
    assert projected is not state
    assert projected.revision == 1
    assert projected.quest_stage["lantern-watch"] == 1
    assert projected.flags["wet"] is True
    assert projected.journal_head == state.journal_head
    assert projected.era_engine == "meadow"
    assert state.quest_stage == {}
    assert state.flags == {}


def test_clean_pass_promotes_once_and_double_submit_does_not_change_revision():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 1}, {"wet": True}))
    assert gate.review().verdicts[0].can_promote is True
    promoted = gate.promote("pass-a", reviewer_id="Mara Quill")
    assert promoted is ledger.state
    assert promoted.revision == 1
    assert promoted.quest_stage["lantern-watch"] == 1
    assert promoted.flags["wet"] is True
    digest = live_canon_digest(ledger)
    with pytest.raises(AuthoringDriftError, match="double-submit"):
        gate.promote("pass-a", reviewer_id="Mara Quill")
    assert ledger.state.revision == 1
    assert ledger.state is promoted
    assert live_canon_digest(ledger) == digest
    assert ledger.state.quest_stage["lantern-watch"] == 1


def test_second_fresh_pass_drifts_after_the_first_promotion():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 0}))
    gate.submit(_patch("pass-b", {"well-path": 1}))
    assert gate.review().contested_keys == ()
    assert all(verdict.can_promote is True for verdict in gate.review().verdicts)
    gate.promote("pass-a", reviewer_id="Mara Quill")
    assert ledger.state.revision == 1
    assert ledger.state.quest_stage["lantern-watch"] == 0
    with pytest.raises(AuthoringDriftError, match="drifted"):
        gate.promote("pass-b", reviewer_id="Mara Quill")
    assert ledger.state.revision == 1
    assert "well-path" not in ledger.state.quest_stage


def test_uncontested_pass_promotes_while_siblings_stay_unpromoted():
    ledger = _ledger()
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 0}))
    gate.submit(_patch("pass-b", {"lantern-watch": 1}))
    gate.submit(_patch("pass-c", {"well-path": 1}, {"wind": True}))
    report = gate.review()
    by_id = {verdict.patch_id: verdict for verdict in report.verdicts}
    assert by_id["pass-a"].can_promote is False
    assert by_id["pass-b"].can_promote is False
    assert by_id["pass-c"].can_promote is True
    promoted = gate.promote("pass-c", reviewer_id="Mara Quill")
    assert promoted.revision == 1
    assert promoted.quest_stage["well-path"] == 1
    assert promoted.flags["wind"] is True
    assert "lantern-watch" not in promoted.quest_stage
    with pytest.raises(AuthoringDriftError, match="drifted"):
        gate.promote("pass-a", reviewer_id="Mara Quill")
    assert ledger.state.revision == 1


def test_promotion_does_not_enroll_a_commit_actor_or_weaken_event_commit():
    ledger = _ledger()
    keys_before = dict(ledger.keys)
    gate = AuthoringGate(ledger)
    gate.submit(_patch("pass-a", {"lantern-watch": 1}))
    gate.promote("pass-a", reviewer_id="Mara Quill")
    assert dict(ledger.keys) == keys_before
    assert "Mara Quill" not in ledger.keys
    page = RPGEventPage(
        "rain-flag",
        5,
        (EnvironmentalTrigger("rain_mm_h", "above", 1.0),),
        (RPGEventAction("set_flag", "world", "wet", "true"),),
    )
    proposal = ledger.propose(page, current={"rain_mm_h": 4}, actor="scout", now_ms=5000)
    with pytest.raises(EventAuthorityError, match="unauthorized commit"):
        ledger.commit(
            proposal.proposal_id,
            actor="Mara Quill",
            expected_canon_digest=live_canon_digest(ledger),
            now_ms=6000,
        )
    assert ledger.state.revision == 1
    assert "Mara Quill" not in ledger.keys
    committed = ledger.commit(
        proposal.proposal_id,
        actor="warden",
        expected_canon_digest=proposal.canon_digest,
        now_ms=6000,
    )
    assert committed.state.revision == 2
    assert committed.state.flags["wet"] is True
    assert committed.state.quest_stage["lantern-watch"] == 1
    with pytest.raises(EventAuthorityError, match="double-submit"):
        ledger.commit(
            proposal.proposal_id,
            actor="warden",
            expected_canon_digest=live_canon_digest(ledger),
            now_ms=7000,
        )
    assert ledger.state.revision == 2


__all__ = tuple(name for name in globals() if name.startswith("test_"))
