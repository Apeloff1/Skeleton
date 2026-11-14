"""Tests for the GameForge 7-step conductor (#807)."""
from __future__ import annotations

import json

import pytest

from skeleton.gameforge import (
    STEPS, BudgetError, ConductorConfig, Era, EraBindingError, EraRegistry, GameForgeConductor, InputError,
    IntegrityError, PlanError, Rung, StepOrderError, UnsafeStateError, VisionRequest, canonical_json, digest,
    verify_manifest,
)
from skeleton.gameforge.errors import LADDER, most_severe
from skeleton.gameforge.manifest import GENESIS, ReceiptLog
from skeleton.gameforge.plans import (CockpitPlan, Control, Feature, Mechanic, PrototypePlan, Region, SnowballPlan,
                                      WorldPlan, slugify)
from skeleton.gameforge import steps as S
from skeleton.gameforge.safety import screen_paths, screen_script, screen_text

REQ = {"title": "Lantern Run", "pitch": "Carry light through caves", "genre": "platformer",
       "pillars": ["light", "speed"], "target_minutes": 15}


def run(req=None, **cfg):
    return GameForgeConductor(config=ConductorConfig(**cfg)).run(req or REQ)


# --- happy path & determinism -------------------------------------------
def test_full_run_ok():
    r = run()
    assert r.ok and r.completed == list(STEPS) and r.error is None


def test_steps_order_is_seven():
    assert STEPS == ("vision", "snowball", "prototype", "mass_forge", "world", "cockpit", "export")


def test_manifest_deterministic_across_runs():
    assert run().manifest.to_json() == run().manifest.to_json()


def test_manifest_digest_changes_with_input():
    assert run().manifest.manifest_digest != run({**REQ, "title": "Other"}).manifest.manifest_digest


def test_manifest_verifies_roundtrip():
    r = run()
    verify_manifest(json.loads(r.manifest.to_json()), r.artifacts)


def test_manifest_artifacts_sorted():
    paths = [p for p, _ in run().manifest.artifacts]
    assert paths == sorted(paths) and paths


def test_receipts_chain_from_genesis():
    m = run().manifest
    assert m.receipts[0].prev == GENESIS and len(m.receipts) == 7


def test_full_run_returns_links():
    links = GameForgeConductor().full_run(REQ)
    assert len(links) == 7 and len(set(links)) == 7


@pytest.mark.parametrize("genre", sorted(S._GENRE_LOOPS))
def test_every_genre_runs(genre):
    assert run({**REQ, "genre": genre}).ok


@pytest.mark.parametrize("era", ["HOUSE_ERA", "PIXEL_8BIT", "PIXEL_16BIT", "LOWPOLY_3D"])
def test_every_builtin_era_runs(era):
    r = run({**REQ, "era": era})
    assert r.ok and r.manifest.era == era


@pytest.mark.parametrize("target", ["web", "desktop", "bundle"])
def test_targets(target):
    assert run(target=target).manifest.to_dict()["metadata"]["target"] == target


# --- era binding ----------------------------------------------------------
def test_unknown_era_refused():
    r = run({**REQ, "era": "NOPE"})
    assert not r.ok and isinstance(r.error, EraBindingError)


def test_era_drift_refused():
    c = GameForgeConductor()
    c.run_step("vision", REQ)
    with pytest.raises(EraBindingError):
        c.run_step("snowball", era_key="PIXEL_8BIT")


def test_era_override_at_run():
    assert run_era("PIXEL_16BIT").manifest.era == "PIXEL_16BIT"


def run_era(k):
    return GameForgeConductor().run(REQ, era_key=k)


def test_pixel_era_excludes_models():
    r = run({**REQ, "era": "PIXEL_8BIT"})
    assert not any(p.startswith("models/") for p, _ in r.manifest.artifacts)


def test_registry_extend_only():
    reg = EraRegistry()
    e = Era("NEW_ERA", "n", 1, ("#000",), frozenset({"script"}), 10)
    reg.register(e)
    reg.register(e)  # idempotent
    with pytest.raises(EraBindingError):
        reg.register(Era("NEW_ERA", "changed", 1, ("#000",), frozenset({"script"}), 10))


def test_registry_rejects_bad_key():
    with pytest.raises(InputError):
        EraRegistry().register(Era("bad key!", "x", 1, (), frozenset(), 1))


def test_custom_era_disallowing_sprites_runs():
    reg = EraRegistry()
    reg.register(Era("TEXT_ERA", "text", 0, ("#000",), frozenset({"script", "sound", "music"}), 100))
    r = GameForgeConductor(registry=reg).run({**REQ, "era": "TEXT_ERA"})
    assert r.ok and not any(p.startswith("sprites/") for p, _ in r.manifest.artifacts)


# --- error ladder ---------------------------------------------------------
def test_ladder_rungs_ascending():
    assert [e.rung for e in LADDER] == sorted(e.rung for e in LADDER)
    assert LADDER[-1].rung is Rung.UNSAFE


def test_most_severe():
    errs = [InputError("a"), UnsafeStateError("b"), PlanError("c")]
    assert isinstance(most_severe(errs), UnsafeStateError) and most_severe([]) is None


def test_error_to_dict_stable():
    d = PlanError("x", step="world", detail={"b": 1, "a": 2}).to_dict()
    assert d["code"] == "gameforge.plan" and list(d["detail"]) == ["a", "b"] and d["rung"] == 2


def test_missing_field_input_error():
    r = run({"title": "x", "genre": "rpg"})
    assert isinstance(r.error, InputError) and r.manifest is None


def test_unknown_field_input_error():
    assert isinstance(run({**REQ, "evil": 1}).error, InputError)


def test_bad_genre_plan_error():
    assert isinstance(run({**REQ, "genre": "opera"}).error, PlanError)


def test_too_many_pillars():
    assert isinstance(run({**REQ, "pillars": list("abcdef")}).error, PlanError)


def test_target_minutes_range():
    assert isinstance(run({**REQ, "target_minutes": 0}).error, PlanError)


def test_unsafe_pitch_refused():
    r = run({**REQ, "pitch": "a game that installs ransomware"})
    assert isinstance(r.error, UnsafeStateError) and r.completed == []


def test_unsafe_overlong_text():
    with pytest.raises(UnsafeStateError):
        screen_text("vision", "x" * 5000)


def test_unsafe_script_refused():
    with pytest.raises(UnsafeStateError):
        screen_script("export", "a.gs", "os.system('rm')")


@pytest.mark.parametrize("p", ["/etc/passwd", "../x", "a\\b", "c:x"])
def test_unsafe_paths(p):
    with pytest.raises(UnsafeStateError):
        screen_paths("export", [p])


def test_budget_clips_optional_assets():
    r = run(budget_bytes=60_000)
    assert r.ok and r.plans["mass_forge"].clipped
    assert r.plans["mass_forge"].total_bytes <= 60_000


def test_budget_too_small_refused():
    r = run(budget_bytes=100)
    assert isinstance(r.error, BudgetError) and r.completed == ["vision", "snowball", "prototype"]


def test_nonpositive_budget():
    assert isinstance(run(budget_bytes=0).error, BudgetError)


def test_bad_target():
    assert isinstance(run(target="moon").error, InputError)


def test_bad_regions():
    assert isinstance(run(regions=0).error, InputError)


# --- ordering -------------------------------------------------------------
def test_out_of_order_refused():
    with pytest.raises(StepOrderError):
        GameForgeConductor().run_step("world")


def test_replay_refused():
    c = GameForgeConductor()
    c.run_step("vision", REQ)
    with pytest.raises(StepOrderError):
        c.run_step("vision", REQ)


def test_invalid_step_name():
    with pytest.raises(InputError):
        GameForgeConductor().run_step("deploy")


def test_vision_requires_request():
    with pytest.raises(InputError):
        GameForgeConductor().run_step("vision")


def test_manifest_before_export_refused():
    c = GameForgeConductor()
    c.run_step("vision", REQ)
    with pytest.raises(StepOrderError):
        c.manifest()


def test_next_step_progression():
    c = GameForgeConductor()
    assert c.next_step == "vision"
    c.run_step("vision", REQ)
    assert c.next_step == "snowball"


def test_hooks_called_in_order():
    seen = []
    GameForgeConductor(hooks={s: (lambda st, p: seen.append(st)) for s in STEPS}).run(REQ)
    assert seen == list(STEPS)


def test_run_resets_state():
    c = GameForgeConductor()
    c.run(REQ)
    r = c.run(REQ)
    assert r.ok and len(c.log.receipts) == 7


# --- integrity ------------------------------------------------------------
def test_tampered_manifest_detected():
    d = json.loads(run().manifest.to_json())
    d["game_id"] = "evil"
    with pytest.raises(IntegrityError):
        verify_manifest(d)


def test_tampered_artifact_detected():
    r = run()
    arts = dict(r.artifacts)
    arts["world.txt"] = b"x"
    with pytest.raises(IntegrityError):
        verify_manifest(r.manifest.to_dict(), arts)


def test_missing_artifact_detected():
    r = run()
    arts = dict(r.artifacts)
    arts.pop("controls.txt")
    with pytest.raises(IntegrityError):
        verify_manifest(r.manifest.to_dict(), arts)


def test_schema_mismatch():
    d = run().manifest.to_dict()
    d["schema"] = "x"
    with pytest.raises(IntegrityError):
        verify_manifest(d)


def test_receipt_log_tamper():
    log = ReceiptLog()
    log.append("vision", "E", {"a": 1})
    log.append("snowball", "E", {"b": 2})
    object.__setattr__(log.receipts[1], "prev", GENESIS)
    with pytest.raises(IntegrityError):
        log.verify()


def test_mutated_plan_detected():
    c = GameForgeConductor()
    c.run(REQ)
    c.plans["world"] = S.world(c.plans["vision"], c.binding.era, 3)
    with pytest.raises(IntegrityError):
        c.manifest()


# --- canonical json -------------------------------------------------------
def test_canonical_json_sorted_compact():
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'


def test_canonical_sets_sorted():
    assert canonical_json({"s": {3, 1, 2}}) == '{"s":[1,2,3]}'


def test_canonical_rejects_nan():
    with pytest.raises(InputError):
        digest({"x": float("nan")})


def test_canonical_rejects_nonstr_keys():
    with pytest.raises(InputError):
        digest({1: "a"})


def test_canonical_rejects_objects():
    with pytest.raises(InputError):
        digest({"x": object()})


# --- plan validators ------------------------------------------------------
def test_slugify():
    assert slugify("Lantern Run!") == "lantern-run"
    with pytest.raises(InputError):
        slugify("!!!")


def _vision():
    return S.vision(VisionRequest.from_mapping(REQ))


def test_snowball_needs_must():
    v = _vision()
    with pytest.raises(PlanError):
        SnowballPlan(v.game_id, ("a", "b"), (Feature("f", "light", 2, 1),)).validate(v)


def test_snowball_unknown_pillar():
    v = _vision()
    with pytest.raises(PlanError):
        SnowballPlan(v.game_id, ("a", "b"), (Feature("f", "nope", 1, 1),)).validate(v)


def test_prototype_must_cover_musts():
    v = _vision()
    s = S.snowball(v)
    with pytest.raises(PlanError):
        PrototypePlan(v.game_id, (), 10).validate(s)


def test_world_unreachable():
    w = WorldPlan("g", 1, (Region("a", (), 1), Region("b", (), 1)), "a")
    with pytest.raises(PlanError):
        w.validate(100)


def test_world_entity_cap():
    with pytest.raises(PlanError):
        WorldPlan("g", 1, (Region("a", (), 50),), "a").validate(10)


def test_world_deterministic_and_connected():
    v = _vision()
    era = EraRegistry().get("HOUSE_ERA")
    assert S.world(v, era, 12) == S.world(v, era, 12)


def test_cockpit_conflicting_bindings():
    p = PrototypePlan("g", (Mechanic("m", "f", ("jump",)),), 10)
    with pytest.raises(PlanError):
        CockpitPlan("g", (Control("jump", "X"), Control("pause", "X")), (), ("remappable_controls",)).validate(p)


def test_cockpit_requires_remap():
    p = PrototypePlan("g", (Mechanic("m", "f", ("jump",)),), 10)
    with pytest.raises(PlanError):
        CockpitPlan("g", (Control("jump", "X"),), (), ()).validate(p)


def test_cockpit_covers_all_verbs():
    r = run()
    verbs = {v for m in r.plans["prototype"].mechanics for v in m.verbs}
    assert verbs <= {c.action for c in r.plans["cockpit"].controls}


def test_result_to_dict_serializable():
    json.dumps(run().to_dict())
    json.dumps(run(budget_bytes=1).to_dict())


# --- legacy API intact ----------------------------------------------------
def test_legacy_conductors_still_import():
    from skeleton.gameforge.conductor_final import GameForgeConductorFinal
    from skeleton.gameforge.conductor_e2e_closed import GameForgeE2EClosed
    assert len(GameForgeConductorFinal().full_run()) == 7
    assert GameForgeE2EClosed is not None
