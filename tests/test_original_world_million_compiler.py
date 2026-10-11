"""Million-world hierarchy: meaningful genre modes, progression and audited counts."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_million_compiler import (
    ADVANCED_CONFIGURATIONS, MODE_FOUNDATIONS,
    ADVANCED_VERSION, advanced_at, advanced_for,
    advanced_from_id, advanced_from_seed, advanced_inventory,
    mode_at, page_advanced,
)
from skeleton.game.generation.original_world_million_runtime import (
    AdvancedAction, create_advanced, replay_advanced,
    restore_advanced, save_advanced, step_advanced, validate_game,
)
from skeleton.game.generation.original_world_play_forms import (
    PLAY_FORMS, PROGRESSION_LAWS,
)

GENRE_FIRST_ACTION = {
    "platform": AdvancedAction("mode", "jump"),
    "puzzle": AdvancedAction("mode", "toggle", target=0),
    "tactics": AdvancedAction("mode", "strike"),
    "survival": AdvancedAction("mode", "scavenge"),
    "colony": AdvancedAction("mode", "construct"),
    "racing": AdvancedAction("mode", "accelerate"),
    "stealth": AdvancedAction("mode", "sneak"),
    "commerce": AdvancedAction("mode", "buy"),
    "exploration": AdvancedAction("mode", "explore"),
    "rhythm": AdvancedAction("mode", "tap", target=0),
}


def advance(state, action):
    return step_advanced(state, action)[0]


def test_100k_and_million_contracts_not_falsely_called_individually_authored() -> None:
    assert MODE_FOUNDATIONS == 102_400 == 10_240 * 10
    assert ADVANCED_CONFIGURATIONS == 1_228_800 == 102_400 * 12
    counts = advanced_inventory()
    assert counts["mechanically_mode_bound_foundation_entries"] == 102400
    assert counts["advanced_structured_configuration_entries"] == 1228800
    assert counts["exceeds_100k_composed_foundations"]
    assert counts["exceeds_1m_advanced_configurations"]
    assert counts["individually_handwritten_advanced_worlds"] == 0
    assert counts["fully_native_verified_games"] == 0
    assert counts["style_hardware_era_or_seed_multipliers"] == 0
    assert counts["index_ranges_are_mutually_nested_not_additive"]


def test_ten_authored_controls_and_twelve_continuations_are_real_distinct_specs() -> None:
    assert len(PLAY_FORMS) == 10
    assert len(PROGRESSION_LAWS) == 12
    assert len({p.player_loop.casefold() for p in PLAY_FORMS}) == 10
    assert len({p.causal_contract.casefold() for p in PROGRESSION_LAWS}) == 12
    assert len({p.continuation_policy for p in PROGRESSION_LAWS}) >= 5
    assert len({verb for p in PLAY_FORMS for verb in p.mechanics}) == 30
    assert all(p.win_criterion and p.control_law and p.difficulty_pressure for p in PLAY_FORMS)
    assert all(a.causal_contract and a.setback_law for a in PROGRESSION_LAWS)


@pytest.mark.parametrize("index", [
    0, 1, 11, 12, 119, 120, 121, 959, 960, 961, 11231,
    120000, 655359, 900000, 1228799,
])
def test_boundary_unranking_roundtrip_and_immutable_source(index) -> None:
    law = advanced_at(index)
    assert law.index == index
    assert law.as_dict()["index"] == str(index)
    assert law.design_id == advanced_from_id(law.advanced_id).design_id
    assert law.mode.base.foundation_index == index // 120
    assert law.mode.form == PLAY_FORMS[(index // 12) % 10]
    assert law.arc == PROGRESSION_LAWS[index % 12]
    assert advanced_for(
        law.mode.base.foundation_index,
        law.mode.form.form_id, law.arc.arc_id,
    ) == law
    data = law.as_dict()
    data["mode"]["form"]["player_loop"] = "corrupted"
    assert advanced_at(index).mode.form.player_loop != "corrupted"
    assert law.provenance == "composed-authored-laws-with-executable-modes"


def test_all_mode_foundations_get_distinct_causal_form_identities() -> None:
    seen = set()
    for base in range(10240):
        for form in range(10):
            index = base * 10 + form
            mode = mode_at(index)
            assert mode.mode_index == index
            assert mode.mode_id not in seen
            assert mode.base.foundation_index == base
            assert mode.form == PLAY_FORMS[form]
            seen.add(mode.mode_id)
    assert len(seen) == MODE_FOUNDATIONS


def test_million_namespace_is_rank_bijective_across_wide_sample() -> None:
    sample = {i * 120 for i in range(10240)}
    sample.update(i * 12 for i in range(0, 102400, 31))
    sample.update((i * 104729) % ADVANCED_CONFIGURATIONS for i in range(4096))
    seen = set()
    for index in sample:
        law = advanced_at(index)
        assert law.design_id not in seen
        seen.add(law.design_id)
    assert len(seen) == len(sample)
    assert advanced_from_seed("eight-era-demo") == advanced_from_seed("eight-era-demo")


def test_lazy_paging_never_materializes_the_million() -> None:
    assert [x.index for x in page_advanced(start=1228797, limit=24)] == [
        1228797, 1228798, 1228799,
    ]
    assert len(list(page_advanced(start=0, limit=64))) == 64
    assert not list(page_advanced(start=ADVANCED_CONFIGURATIONS, limit=5))
    for bad in ({"start": -1}, {"start": 1_228_801},
                {"limit": 0}, {"limit": 300}, {"limit": True}):
        with pytest.raises(FoundationError):
            list(page_advanced(**bad))


@pytest.mark.parametrize("bad", [-1, 1228800, True, 1.5, "1", None])
def test_illegal_advanced_indices_are_rejected(bad) -> None:
    with pytest.raises(FoundationError):
        advanced_at(bad)


@pytest.mark.parametrize("bad", ["", "adv-01", "adv-01234567",
                                   "adv-0000000x", "adv-9999999", None])
def test_invalid_advanced_ids_are_not_guessed(bad) -> None:
    with pytest.raises(FoundationError):
        advanced_from_id(bad)


def test_all_120_forms_and_progressions_support_actual_events() -> None:
    outcome_pairs = set()
    for form in PLAY_FORMS:
        for arc in PROGRESSION_LAWS:
            law = advanced_for(0, form.form_id, arc.arc_id)
            state = create_advanced(law.advanced_id)
            played, receipt = step_advanced(state, GENRE_FIRST_ACTION[form.form_id])
            assert receipt.event_id == played.event_head
            assert receipt.layer == "mode"
            assert played.events == 1
            assert played.mode.actions == 1
            assert played != state
            played = advance(played, AdvancedAction("arc", "reflect"))
            assert played.arc.legacy == 1
            played = advance(played, AdvancedAction("causal", "end_turn"))
            assert played.causal.tick == 1
            assert played.events == 3
            validate_game(played)
            outcome_pairs.add((form.form_id, arc.arc_id))
    assert len(outcome_pairs) == 120


def test_modes_have_distinct_actual_rule_transitions() -> None:
    effects = set()
    for form in PLAY_FORMS:
        law = advanced_for(0, form.form_id, "chapters")
        state = create_advanced(law.advanced_id)
        after = advance(state, GENRE_FIRST_ACTION[form.form_id])
        footprint = tuple(
            (key, getattr(after.mode, key))
            for key in after.mode.__dataclass_fields__
            if getattr(after.mode, key) != getattr(state.mode, key)
        )
        assert footprint
        effects.add(footprint)
    assert len(effects) == 10


def test_puzzle_has_real_bitmask_gate_not_a_cosmetic_progress_counter() -> None:
    state = create_advanced(advanced_for(0, "puzzle", "chapters").advanced_id)
    with pytest.raises(FoundationError):
        advance(state, AdvancedAction("mode", "pass"))
    state = advance(state, AdvancedAction("mode", "toggle", target=0))
    state = advance(state, AdvancedAction("mode", "toggle", target=2))
    assert state.mode.switches == 5
    state = advance(state, AdvancedAction("mode", "pass"))
    assert state.mode.cleared
    state = advance(state, AdvancedAction("arc", "commit"))
    assert state.arc.completed
    assert state.arc.chapter == 1


def test_rhythm_tracks_timing_and_wrong_notes_dont_fake_combos() -> None:
    state = create_advanced(advanced_for(0, "rhythm", "endless").advanced_id)
    state = advance(state, AdvancedAction("mode", "tap", target=2))
    assert state.mode.combo == 0 and state.mode.beat == 1
    state = advance(state, AdvancedAction("causal", "end_turn"))
    state = advance(state, AdvancedAction("mode", "tap", target=2))
    assert state.mode.combo == 1
    for _ in range(3):
        state = advance(state, AdvancedAction("causal", "end_turn"))
        note = (0, 2, 1, 3)[state.mode.beat % 4]
        state = advance(state, AdvancedAction("mode", "tap", target=note))
    assert state.mode.combo == 4
    assert state.mode.cleared
    assert not state.arc.completed


def test_colony_requires_real_housing_and_food_for_population() -> None:
    state = create_advanced(advanced_for(0, "colony", "civilization").advanced_id)
    state = advance(state, AdvancedAction("mode", "construct", amount=2))
    state = advance(state, AdvancedAction("mode", "cultivate"))
    assert state.causal.supplies == 5
    for _ in range(2):
        state = advance(state, AdvancedAction("causal", "end_turn"))
    assert state.mode.housing == 3 and state.mode.population == 3
    assert state.mode.cleared
    assert state.mode.colony_food < 10


def test_stealth_requires_distraction_to_avoid_capture_pressure() -> None:
    state = create_advanced(advanced_for(0, "stealth", "branching").advanced_id)
    for _ in range(3):
        state = advance(state, AdvancedAction("mode", "sneak", amount=3))
    state = advance(state, AdvancedAction("mode", "distract"))
    state = advance(state, AdvancedAction("causal", "end_turn"))
    state = advance(state, AdvancedAction("mode", "sneak"))
    assert state.mode.course == 10
    assert state.mode.alert < 10
    assert state.mode.cleared


def test_all_12_progression_clocks_drive_real_consequences_over_time() -> None:
    fingerprints = []
    for arc in PROGRESSION_LAWS:
        state = create_advanced(advanced_for(0, "survival", arc.arc_id).advanced_id)
        for _ in range(8):
            state = advance(state, AdvancedAction("causal", "end_turn"))
        assert state.causal.tick == 8
        assert state.arc.checkpoint >= 3
        fingerprints.append((arc.arc_id, asdict(state.arc),
                             state.causal.trust, state.causal.hazard,
                             state.mode.warmth, state.mode.deposit))
    assert len({json.dumps(x, sort_keys=True) for x in fingerprints}) == 12


def test_recurring_no_win_condition_continues_even_with_success() -> None:
    state = create_advanced(advanced_for(0, "puzzle", "endless").advanced_id)
    state = advance(state, AdvancedAction("mode", "toggle", target=0))
    state = advance(state, AdvancedAction("mode", "toggle", target=2))
    state = advance(state, AdvancedAction("mode", "pass"))
    assert state.mode.cleared and not state.arc.completed
    state = advance(state, AdvancedAction("causal", "end_turn"))
    assert state.causal.tick == 1
    with pytest.raises(FoundationError):
        advance(replace(state, arc=replace(state.arc, completed=True)),
                AdvancedAction("causal", "end_turn"))


def test_persistent_branch_choice_has_real_cost_and_durable_effect() -> None:
    base = advanced_for(0, "platform", "branching")
    state = create_advanced(base.advanced_id)
    care = advance(state, AdvancedAction("arc", "choose", option="care"))
    power = advance(state, AdvancedAction("arc", "choose", option="power"))
    assert care.arc.branch == "care" and power.arc.branch == "power"
    assert care.causal.supplies < state.causal.supplies
    assert power.causal.trust < state.causal.trust
    for _ in range(4):
        care = advance(care, AdvancedAction("causal", "end_turn"))
        power = advance(power, AdvancedAction("causal", "end_turn"))
    assert care.causal.trust != power.causal.trust
    assert care.causal.hazard != power.causal.hazard
    with pytest.raises(FoundationError):
        advance(care, AdvancedAction("arc", "choose", option="power"))


def test_evidence_receipts_save_replay_and_corruption_detection() -> None:
    law = advanced_for(7777, "tactics", "dynasty")
    script = (
        AdvancedAction("mode", "guard"),
        AdvancedAction("mode", "strike"),
        AdvancedAction("arc", "reflect"),
        AdvancedAction("causal", "end_turn"),
        AdvancedAction("causal", "intervene"),
    )
    a, receipts = replay_advanced(law.index, script)
    b, again = replay_advanced(law.index, script)
    assert a == b and receipts == again
    assert len({r.event_id for r in receipts}) == len(receipts)
    assert restore_advanced(save_advanced(a)) == a
    forged = json.loads(save_advanced(a))
    forged["payload"]["mode"]["wallet"] = 9999
    with pytest.raises(FoundationError):
        restore_advanced(json.dumps(forged))


@pytest.mark.parametrize("bad", [
    AdvancedAction("unexpected", "tap"),
    AdvancedAction("mode", "warp"),
    AdvancedAction("mode", "jump", amount=True),
    AdvancedAction("mode", "jump", amount=0),
    AdvancedAction("mode", "jump", amount=4),
    AdvancedAction("arc", "choose", option="override"),
])
def test_invalid_commands_cannot_mutate_immutable_states(bad) -> None:
    state = create_advanced(advanced_for(0, "platform", "chapters").advanced_id)
    initial = asdict(state)
    with pytest.raises(FoundationError):
        step_advanced(state, bad)
    assert asdict(state) == initial
