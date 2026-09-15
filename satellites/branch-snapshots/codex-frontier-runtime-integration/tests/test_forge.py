"""Tests for the Universal Forge — SOTA era compile + Godot emit."""

try:
    import pytest
except ImportError:  # pragma: no cover
    class pytest:  # type: ignore
        class raises:
            def __init__(self, exc):
                self.exc = exc
            def __enter__(self):
                return self
            def __exit__(self, t, v, tb):
                if t is None:
                    raise AssertionError("did not raise")
                return issubclass(t, self.exc)

from skeleton.forge import Forge, Port, compile_era, list_eras, emit_godot
from skeleton.forge.archetypes import default_library
from skeleton.forge.planner import MaterialisationPlanner
from skeleton.kernel.errors import BlueprintError, MaterialisationError


def make_linear(forge: Forge):
    bp = forge.new_blueprint("etl")
    forge.instantiate(bp, "source", "in")
    forge.instantiate(bp, "transform", "mid")
    forge.instantiate(bp, "sink", "out")
    bp.connect(("in", "out"), ("mid", "in"))
    bp.connect(("mid", "out"), ("out", "in"))
    return bp


class TestForge:
    def test_stdlib_kinds(self):
        kinds = Forge().available_kinds()
        for k in ("sink", "source", "state_store", "transform", "player", "heat", "jeeves", "extract"):
            assert k in kinds

    def test_materialise_order(self):
        forge = Forge()
        result = forge.materialise(make_linear(forge))
        assert result["execution_order"] == ["in", "mid", "out"]
        assert result["era"] == "extraction_now"
        assert result["primary_dps"] > 0
        assert "plan" in result

    def test_type_mismatch_detected(self):
        forge = Forge()
        bp = forge.new_blueprint("bad")
        forge.instantiate(bp, "source", "s")
        forge.instantiate(bp, "state_store", "store")
        bp.connect(("s", "out"), ("store", "write"))  # event -> state
        problems = bp.validate()
        assert any("type mismatch" in p for p in problems)

    def test_cycle_detected(self):
        forge = Forge()
        bp = forge.new_blueprint("cyclic")
        forge.instantiate(bp, "transform", "a")
        forge.instantiate(bp, "transform", "b")
        bp.connect(("a", "out"), ("b", "in"))
        bp.connect(("b", "out"), ("a", "in"))
        assert any("cycle" in p for p in bp.validate())
        with pytest.raises(MaterialisationError):
            forge.materialise(bp)

    def test_unknown_kind_rejected(self):
        forge = Forge()
        bp = forge.new_blueprint("x")
        with pytest.raises(BlueprintError):
            forge.instantiate(bp, "flux_capacitor", "f1")

    def test_port_direction_enforced(self):
        with pytest.raises(BlueprintError):
            Port("p", "event", "sideways")

    def test_custom_kind(self):
        forge = Forge()
        forge.register_kind("aggregator",
                            (Port("in", "event", "in"), Port("out", "event", "out")))
        assert "aggregator" in forge.available_kinds()


class TestEraCompile:
    def test_catalog(self):
        eras = list_eras()
        assert "extraction_now" in eras
        assert "soulslike" in eras
        assert len(eras) >= 7

    def test_soulslike_slower_tougher(self):
        a = compile_era("extraction_now")
        b = compile_era("soulslike")
        assert b["player"]["speed"] < a["player"]["speed"]
        elite_a = next(e for e in a["enemies"] if e["id"] == "elite")
        elite_b = next(e for e in b["enemies"] if e["id"] == "elite")
        assert elite_b["ttk_target"] > elite_a["ttk_target"]

    def test_hp_is_dps_times_ttk(self):
        p = compile_era("boomer_shooter")
        trash = next(e for e in p["enemies"] if e["id"] == "trash")
        assert trash["hp"] == round(p["primary_dps"] * trash["ttk_target"], 1)


class TestGodotEmit:
    def test_files_and_era_inject(self):
        pack = compile_era("soulslike")
        files = emit_godot(pack, title="SOUL-RUN")
        assert "project.godot" in files
        assert "Jeeves=" in files["project.godot"]
        assert "W_HEAT_CRITICAL := 0.85" in files["scripts/autoloads/jeeves.gd"]
        assert "speed: float = 155.0" in files["scripts/player/player_controller.gd"]
        assert "kinetic_heavy" in files["scripts/autoloads/forge_manager.gd"]
        assert "collapse_max: float = 480.0" in files["scripts/autoloads/game_state.gd"]

    def test_materialise_godot_target(self):
        forge = Forge()
        bp = default_library().build(forge, "extraction")
        art = forge.materialise(bp, era="boomer_shooter", target="godot")
        assert art["era"] == "boomer_shooter"
        assert art["file_count"] >= 7
        assert "scripts/autoloads/heat_system.gd" in art["files"]
        assert "220.0" in art["files"]["scripts/player/player_controller.gd"]


class TestPlannerFromBlueprint:
    def test_waves(self):
        forge = Forge()
        bp = make_linear(forge)
        plan = MaterialisationPlanner().plan_blueprint(bp)
        assert plan.waves[0].systems == ("in",)
        assert "out" in plan.waves[-1].systems
        assert plan.critical_path[0] == "in"
