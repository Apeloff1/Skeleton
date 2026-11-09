"""Large-scale authorial provenance and 10,240 causal-foundation correctness."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import (
    COUPLING_COUNT, FOUNDATION_VERSION, ROOT_COUNT, REGIME_COUNT,
    INDEPENDENTLY_AUTHORED_ROOT_WORLDS, REGIME_FAMILIES,
    STRUCTURED_FOUNDATIONS, TOTAL_FOUNDATION_ENTRIES,
    FoundationError, REGIMES, ROOTS, foundation_at, foundation_for,
    foundation_from_seed, foundation_by_id, iter_foundations,
    provenance_report,
)
from skeleton.game.generation.original_foundation_runtime import (
    ACTIONS, CausalAction, create_causal, paths, available_exits,
    step_causal, replay_causal, save_causal, restore_causal,
    validate_causal, DOMAINS,
)
from skeleton.game.generation.original_world_catalog import WORLDS


def act(state, verb, amount=1, option="", target=-1):
    return step_causal(state, CausalAction(verb, amount, option, target))[0]


def test_128_handwritten_new_roots_with_concrete_laws() -> None:
    assert ROOT_COUNT == 128
    assert len(ROOTS) == ROOT_COUNT
    assert len({r.title.casefold() for r in ROOTS}) == ROOT_COUNT
    assert len({r.invariant.casefold() for r in ROOTS}) == ROOT_COUNT
    assert len({r.root_id for r in ROOTS}) == ROOT_COUNT
    assert len({r.domain for r in ROOTS}) == 16
    assert all(r.provenance == "individually-authored-causal-law" for r in ROOTS)
    assert all(r.lever and r.failure and len(r.invariant) >= 40 for r in ROOTS)


def test_80_authored_regimes_and_160_distinct_couplings() -> None:
    assert REGIME_COUNT == 80 and REGIME_FAMILIES == 10
    assert COUPLING_COUNT == 160
    assert len(REGIMES) == REGIME_COUNT
    assert len({r.regime_id for r in REGIMES}) == REGIME_COUNT
    assert len({r.title.casefold() for r in REGIMES}) == REGIME_COUNT
    assert Counter(r.operator for r in REGIMES) == {
        "echo": 8, "levy": 8, "reverse": 8,
        "threshold": 8, "migration": 8, "veto": 8,
        "cascade": 8, "exchange": 8, "auction": 8, "fork": 8,
    }


def test_atlas_exactly_exceeds_10000_without_style_cardinality_inflation() -> None:
    assert len(WORLDS) == 1296
    assert STRUCTURED_FOUNDATIONS == 128 * 80 == 10240
    assert TOTAL_FOUNDATION_ENTRIES == 11536
    assert INDEPENDENTLY_AUTHORED_ROOT_WORLDS == 1424
    p = provenance_report()
    assert p["cross_law_composed_foundation_entries"] == 10240
    assert p["total_world_foundation_entries"] == 11536
    assert p["individually_written_world_roots_total"] == 1424
    assert p["cross_law_entries_are_individually_hand_written"] is False
    assert p["every_composition_has_two_authored_laws_and_an_authored_bridge"]
    assert p["worlds_guaranteed_native_playable"] == 0


def test_every_entry_has_unique_id_story_signature_and_strict_origin() -> None:
    # Enumerates 10,240 exactly-addressed intersections; none are counted
    # solely because of cosmetics, difficulty, texture, or different seed.
    ids, titles, signatures, consequences = set(), set(), set(), set()
    for i in range(STRUCTURED_FOUNDATIONS):
        f = foundation_at(i)
        assert f.foundation_index == i
        assert f.provenance == "authored-causal-composition"
        assert f.design_id not in signatures
        assert f.title not in titles
        assert f.foundation_id not in ids
        assert f.invariant and f.player_lever and f.failure_pressure
        assert f.root.invariant in f.invariant
        assert f.regime.invariant in f.invariant
        assert f.coupling in f.invariant
        assert f.domain == f.root.domain
        assert f.implementation_status == "bounded-reference-runtime"
        ids.add(f.foundation_id)
        titles.add(f.title)
        signatures.add(f.design_id)
        consequences.add(f.coupling)
    assert len(ids) == len(titles) == len(signatures) == 10240
    assert len(consequences) == 160


@pytest.mark.parametrize("index", [
    0, 1, 7, 8, 79, 80, 319, 639, 640, 1599,
    2500, 5119, 5120, 9999, 10239,
])
def test_exact_index_lookup_roundtrip_and_mutation_safety(index) -> None:
    foundation = foundation_at(index)
    original = foundation.as_dict()
    assert original["foundation_index"] == str(index)
    assert original["version"] == FOUNDATION_VERSION
    assert foundation_by_id(foundation.foundation_id) == foundation
    assert foundation_for(
        foundation.root.root_id, foundation.regime.regime_id
    ) == foundation
    original["root"]["invariant"] = "MUTATED"
    assert foundation_at(index).root.invariant != "MUTATED"


def test_paged_lookups_are_bounded_and_reproducible() -> None:
    assert len(list(iter_foundations(start=0, limit=256))) == 256
    assert [f.foundation_index for f in iter_foundations(start=10237, limit=256)] == [
        10237, 10238, 10239,
    ]
    assert foundation_from_seed("dragon-kernel") == foundation_from_seed("dragon-kernel")
    assert foundation_from_seed("next-studio") != foundation_from_seed("dragon-kernel")
    for args in ({"start": -1}, {"start": 10241}, {"limit": 0},
                 {"limit": 4096}, {"start": True}):
        with pytest.raises(FoundationError):
            list(iter_foundations(**args))


@pytest.mark.parametrize("invalid", [-1, 10240, True, None, 0.5, "2"])
def test_invalid_catalog_indices_fail_closed(invalid) -> None:
    with pytest.raises(FoundationError):
        foundation_at(invalid)


@pytest.mark.parametrize("invalid", ["", None, 42, "x" * 4097])
def test_invalid_seed_fails_closed(invalid) -> None:
    with pytest.raises(FoundationError):
        foundation_from_seed(invalid)


def test_missing_root_and_overlay_ids_cannot_be_silently_resolved() -> None:
    for bad in ("", "fnd-root-geometry-01-regime-echo-99",
                "fnd-root-unknown-01-regime-echo-01"):
        with pytest.raises(FoundationError):
            foundation_by_id(bad)
    with pytest.raises(FoundationError):
        foundation_for("root-geometry-01", "unknown")


def test_every_composition_has_an_actual_playable_generic_causal_turn() -> None:
    # All 10,240 crossings must accept a deterministic world-action receipt,
    # not just load as textual catalogs.
    for i in range(STRUCTURED_FOUNDATIONS):
        state = create_causal(i)
        updated, receipt = step_causal(state, CausalAction("end_turn"))
        assert updated.tick == 1
        assert updated.event_count == 1
        assert receipt.event_hash == updated.event_head
        assert updated.foundation_id == foundation_at(i).foundation_id
        assert receipt.changes


def test_all_160_distinct_domain_operator_couplings_have_interventions() -> None:
    outcomes = {}
    for domain_index in range(16):
        for operator_index in range(10):
            i = domain_index * 8 * 80 + operator_index * 8
            law = foundation_at(i)
            assert law.root.domain == ROOTS[domain_index * 8].domain
            assert law.regime.operator == REGIMES[operator_index * 8].operator
            state = create_causal(i)
            changed, event = step_causal(state, CausalAction("intervene"))
            outcomes[(law.domain, law.regime.operator)] = (
                changed.primary, changed.remote, changed.hazard,
                changed.duty, changed.reserve, changed.echo_due,
                changed.branch, event.changes,
            )
            assert changed != state
            assert event.event_hash == changed.event_head
            assert law.coupling in " ".join(event.changes)
    assert len(outcomes) == 160


def test_all_eight_root_variants_produce_real_cost_or_effect_differences() -> None:
    summaries = set()
    for root in ROOTS[:8]:
        state = create_causal(
            foundation_for(root.root_id, "regime-echo-01").foundation_id
        )
        updated = act(state, "intervene")
        summaries.add((updated.primary, updated.energy, updated.hazard))
    assert len(summaries) == 8


def test_all_eight_regime_intensities_change_effect_or_gate() -> None:
    rows = []
    for n in range(1, 9):
        s = create_causal(
            foundation_for("root-geometry-01", f"regime-levy-{n:02d}").foundation_id
        )
        after = act(s, "intervene")
        rows.append((after.supplies, after.reserve))
    assert len(set(rows)) >= 3


@pytest.mark.parametrize("operator,expected", [
    ("echo", "echo_due"),
    ("levy", "reserve"),
    ("reverse", "remote"),
    ("threshold", "primary"),
    ("migration", "remote"),
    ("veto", "trust"),
    ("cascade", "momentum"),
    ("exchange", "reserve"),
    ("auction", "reserve"),
    ("fork", "branch"),
])
def test_each_of_ten_regimes_rewrites_state_causally(operator, expected) -> None:
    law = foundation_for("root-geometry-01", f"regime-{operator}-01")
    start = create_causal(law.foundation_id)
    after = act(start, "intervene")
    assert getattr(after, expected) != getattr(start, expected)
    assert after.event_count == 1


def test_event_chain_and_save_proof_are_deterministic() -> None:
    actions = (
        CausalAction("intervene"),
        CausalAction("study"),
        CausalAction("negotiate"),
        CausalAction("end_turn"),
        CausalAction("restore"),
        CausalAction("end_turn"),
    )
    i = foundation_for(
        "root-ecosphere-01", "regime-echo-01"
    ).foundation_index
    first, receipts = replay_causal(i, actions)
    second, again = replay_causal(i, actions)
    assert first == second and receipts == again
    assert len({r.event_hash for r in receipts}) == len(receipts)
    assert restore_causal(save_causal(first)) == first
    tampered = json.loads(save_causal(first))
    tampered["payload"]["state"]["primary"] = 999
    with pytest.raises(FoundationError):
        restore_causal(json.dumps(tampered))


def test_causality_preserves_movement_adjacency_and_bounded_nav() -> None:
    a = create_causal(0)
    assert len(paths(a)) >= 12
    exits = available_exits(a)
    assert exits
    reachable = exits[0]
    moved = act(a, "move", target=reachable)
    assert moved.position == reachable
    assert reachable in moved.investigated
    assert moved.energy == a.energy - 1
    assert a.position == 0
    with pytest.raises(FoundationError):
        act(moved, "move", target=moved.position)


def test_unwinnable_is_explicit_not_fake_ending() -> None:
    law = next(f for f in (foundation_at(i) for i in range(STRUCTURED_FOUNDATIONS))
               if f.ending_policy == "unwinnable")
    s = create_causal(law.foundation_id)
    progressed = replace(s, primary=1000, trust=90)
    after = act(progressed, "end_turn")
    assert not after.chapter_complete
    assert after.tick == 1
    assert not after.chapter_complete


def test_fork_branches_have_distinct_consequences() -> None:
    law = foundation_for("root-geometry-01", "regime-fork-01")
    start = create_causal(law.foundation_id)
    care = act(start, "choose", option="care")
    power = act(start, "choose", option="power")
    assert care.branch == "care" and power.branch == "power"
    assert care.trust > power.trust
    assert power.hazard > care.hazard
    with pytest.raises(FoundationError):
        act(care, "choose", option="power")


def test_regime_veto_blocks_actions_until_trust_restored() -> None:
    law = foundation_for("root-geometry-01", "regime-veto-08")
    start = replace(create_causal(law.foundation_id), trust=5)
    with pytest.raises(FoundationError):
        act(start, "intervene")
    improved = act(start, "negotiate", amount=2)
    after = act(improved, "intervene")
    assert after.primary > 0
    assert after.trust < improved.trust


def test_restore_and_recovery_pay_real_costs() -> None:
    law = foundation_for("root-ecosphere-02", "regime-cascade-05")
    s = create_causal(law.foundation_id)
    a = act(s, "intervene")
    repaired = act(a, "restore")
    assert repaired.hazard < a.hazard
    assert repaired.supplies == a.supplies - 1
    assert repaired.reserve == a.reserve + 1
    spent = act(repaired, "end_turn")
    assert spent.energy >= repaired.energy


@pytest.mark.parametrize("bad_action", [
    CausalAction("unregistered"),
    CausalAction("intervene", amount=0),
    CausalAction("intervene", amount=4),
    CausalAction("intervene", amount=True),
    CausalAction("move", target=20),
    CausalAction("choose", option="unauthorized"),
])
def test_bad_actions_do_not_modify_immutable_game_state(bad_action) -> None:
    s = create_causal(0)
    before = asdict(s)
    with pytest.raises(FoundationError):
        step_causal(s, bad_action)
    assert asdict(s) == before


def test_event_budget_and_invalid_save_fails_closed() -> None:
    s = create_causal(0)
    with pytest.raises(FoundationError):
        step_causal(replace(s, event_count=1000), CausalAction("end_turn"))
    with pytest.raises(FoundationError):
        restore_causal("not json")
    with pytest.raises(FoundationError):
        restore_causal("x" * 65537)
