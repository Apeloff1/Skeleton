"""Context substrate — tensor, dodeca, oracle, helix, ledger, snowball, cockpit, run."""
from __future__ import annotations

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

from skeleton.context.cockpit import Cockpit, CockpitError
from skeleton.context.dodeca import ADJ, FACES, VERTICES, Dodecahedron
from skeleton.context.helix import DNAHelix, complement, transcribe
from skeleton.context.ledger import ContextLedger
from skeleton.context.oracle import MOUTHS, VERTEX_FACES, Magic8Ball
from skeleton.context.pipeline import GameForgeRun
from skeleton.context.snowball import WEIGHTS, Snowball
from skeleton.context.tensor import AXES, ContextTensor, detect_era


class TestTensor:
    def test_era_profile_clamped(self):
        t = ContextTensor.from_era("soulslike")
        assert t.era == "soulslike"
        assert 0.8 < t["lethality"] <= 1.0
        assert t["tempo"] < ContextTensor.from_era("boomer_shooter")["tempo"]

    def test_lerp_fingerprint_changes(self):
        a = ContextTensor.from_era("cozy_wholesome")
        b = ContextTensor.from_era("horror_survival")
        mid = a.lerp(b, 0.5)
        assert a.fingerprint() != mid.fingerprint() != b.fingerprint()
        assert abs(mid["risk"] - (a["risk"] + b["risk"]) / 2) < 1e-9

    def test_detect_soulslike(self):
        era, scores = detect_era("a soulslike with bonfire rest and i-frame rolls")
        assert era == "soulslike"
        assert scores["soulslike"] >= 2

    def test_with_axis(self):
        t = ContextTensor.from_era("extraction_now").with_axis("risk", 1.5)
        assert t["risk"] == 1.0
        assert len(AXES) == 10


class TestDodeca:
    def test_counts(self):
        assert len(FACES) == 12
        assert len(VERTICES) == 20
        assert all(len(n) == 5 for n in ADJ)
        assert sum(len(n) for n in ADJ) == 60  # 30 undirected edges

    def test_geodesic(self):
        d = Dodecahedron.from_tensor(ContextTensor.from_era("extraction_now"))
        assert d.geodesic("combat", "combat") == 0
        assert d.geodesic("combat", FACES[ADJ[0][0]]) == 1
        # diameter of icosahedral graph is 3
        assert 1 <= d.geodesic("combat", "meta") <= 3

    def test_activations_sum_one(self):
        d = Dodecahedron.from_tensor(ContextTensor.from_era("soulslike"))
        assert abs(sum(d.activations) - 1.0) < 1e-9
        assert d.hottest(1)[0][1] > 1 / 12 / 2


class TestOracle:
    def test_twenty_mouths(self):
        assert len(MOUTHS) == 20
        assert len(VERTEX_FACES) == 20

    def test_deterministic_roll(self):
        t = ContextTensor.from_era("boomer_shooter")
        d = Dodecahedron.from_tensor(t)
        a = Magic8Ball(d).roll(t, nonce=0)
        b = Magic8Ball(d).roll(t, nonce=0)
        assert a.index == b.index
        assert a.text == b.text
        c = Magic8Ball(d).roll(t, nonce=1)
        # nonce may or may not change index; seed must change
        assert a.seed != c.seed


class TestHelix:
    def test_complement_roundtrip(self):
        w = transcribe("operator vision")
        assert complement(complement(w)) == w

    def test_linking_and_nick(self):
        h = DNAHelix()
        h.pair("ingest", "hello", "ingested")
        h.pair("detect", "soulslike please", "soulslike")
        assert h.turns == 2
        sigma0 = h.supercoiling
        h.nick()
        assert h.nicked == 1
        assert h.supercoiling != sigma0
        h.ligate()
        assert h.nicked == 0

    def test_crossover(self):
        a, b = DNAHelix(), DNAHelix()
        for i in range(4):
            a.pair(f"a{i}", "op", "sys")
            b.pair(f"b{i}", "op2", "sys2")
        child = a.crossover(b, cut=2)
        assert child.turns == 4
        assert child.pairs[0].stage.startswith("a")
        assert child.pairs[-1].stage.startswith("b")


class TestLedger:
    def test_verify_and_tamper(self):
        led = ContextLedger()
        led.append("ingest", {"n": 1}, mass=0.06, tensor_fp="abc", leaves=["ingest"])
        assert led.height == 1
        assert led.verify() == []
        led.tamper(1, "n", 99)
        assert any("hash mismatch" in p for p in led.verify())


class TestSnowball:
    def test_mass_conserved(self):
        assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9
        s = Snowball()
        for stage in WEIGHTS:
            s.mark(stage)
        assert s.complete
        assert s.mass == 1.0


class TestCockpit:
    def test_command_language(self):
        c = Cockpit()
        r = c.apply("BIND ERA soulslike")
        assert r["result"]["era"] == "soulslike"
        c.apply("SET AXIS grind 0.99")
        assert c.tensor["grind"] == 0.99
        g = c.apply("BIND GENERATION nes")
        assert g["result"]["generation"] == "8bit"
        roll = c.apply("ROLL ORACLE")
        assert "text" in roll["result"]
        with pytest.raises(CockpitError):
            c.apply("SUMMON DEMON")

    def test_blend_command(self):
        c = Cockpit()
        r = c.apply("BLEND ERA arcade_golden_age soulslike 0.5")
        assert r["ok"]
        assert "~" in r["result"]["era"]
        assert c.blend == ("arcade_golden_age", "soulslike", 0.5)
        mid = ContextTensor.from_era("arcade_golden_age").lerp(
            ContextTensor.from_era("soulslike"), 0.5
        )
        assert abs(c.tensor["tempo"] - mid["tempo"]) < 1e-9

    def test_detect_command(self):
        c = Cockpit()
        r = c.apply("DETECT tarkov raid extract loot heat")
        assert r["result"]["era"] == "extraction_now"


class TestGameForgeRun:
    def test_full_mass(self):
        out = GameForgeRun().execute(
            "soulslike extraction with bonfire rest and estus",
            target="godot",
        )
        assert out["succeeded"]
        assert out["complete"]
        assert out["mass"] == 1.0
        assert out["era"] == "soulslike"
        assert out["ledger"]["valid"] is True
        assert out["helix"]["turns"] >= 9
        assert out["forge"]["file_count"] >= 7
        assert "Heat" in (out["jeeves"]["next"]["text"] + out["jeeves"]["advice"][0]["text"])
        assert "project.godot" in out["files"]
        assert out["build_plan"]["room_bias"] in {"combat", "loot", "heat", "balanced"}
        tscn = out["files"]["scenes/levels/run_level.tscn"]
        assert "Room_r00" in tscn
        assert "instance=ExtResource" in tscn
        assert '"kind": "player"' in out["files"]["data/rooms.json"] or '"kind": "spawn"' in out["files"]["data/rooms.json"]


class TestSim:
    def test_ideal_trash_matches_compiler(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.sim import simulate_session
        for era in ("extraction_now", "soulslike", "boomer_shooter"):
            pack = compile_era(era)
            report = simulate_session(pack)
            trash = next(e for e in report.encounters if e.enemy_id == "trash" and e.mode == "ideal")
            assert trash.killed, era
            assert trash.error <= 0.20, (era, trash.error, trash.measured_ttk, trash.target_ttk)
            assert report.passed, report.notes

    def test_thermal_not_faster_than_ideal(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.sim import simulate_session
        pack = compile_era("extraction_now")
        report = simulate_session(pack)
        ideal = next(e for e in report.encounters if e.enemy_id == "trash" and e.mode == "ideal")
        therm = next(e for e in report.encounters if e.enemy_id == "trash" and e.mode == "thermal")
        assert therm.measured_ttk + 0.2 >= ideal.measured_ttk
        assert report.walk and report.walk["extracted"]

    def test_walk_extracts_and_locks(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.world import generate_rooms
        from skeleton.forge.walk import walk_graph
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        pack = compile_era("soulslike")
        plan = BuilderBrain().plan(pack, tensor=ContextTensor.from_era("soulslike")).to_dict()
        graph = generate_rooms(pack, seed=plan["seed"], plan=plan)
        wr = walk_graph(pack, graph, plan=plan)
        assert wr.extracted, wr.notes
        assert wr.hops >= 1
        assert wr.t + 1e-6 >= wr.bound
        assert wr.path[0] == graph["rooms"][0]["id"]
        assert wr.path[-1] == graph["rooms"][-1]["id"]
        if wr.required_cores:
            assert wr.cores >= wr.required_cores
            # a core source is visited before the extract hop
            kinds = {r["id"]: r["kind"] for r in graph["rooms"]}
            assert any(kinds[r] in {"loot", "combat"} for r in wr.path[:-1])

    def test_walk_disconnected_fails(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.world import generate_rooms
        from skeleton.forge.walk import walk_graph
        pack = compile_era("extraction_now")
        g = generate_rooms(pack)
        g["doors"] = []
        g["edges"] = []
        wr = walk_graph(pack, g, plan={})
        assert not wr.extracted

    def test_thermal_walk_not_faster_than_ideal(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.world import generate_rooms
        from skeleton.forge.walk import walk_graph
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        pack = compile_era("soulslike")
        plan = BuilderBrain().plan(pack, tensor=ContextTensor.from_era("soulslike")).to_dict()
        graph = generate_rooms(pack, seed=plan["seed"], plan=plan)
        ideal = walk_graph(pack, graph, plan=plan, mode="ideal")
        therm = walk_graph(pack, graph, plan=plan, mode="thermal")
        assert ideal.extracted and therm.extracted, (ideal.notes, therm.notes)
        rec = (pack.get("recipes") or [{}])[0]
        interval = 60.0 / max(float(rec.get("rpm") or 360), 1.0)
        assert therm.t + interval * max(1, therm.fights) >= ideal.t
        assert therm.mode == "thermal"
        assert therm.path == ideal.path

    def test_hot_start_slows_fight(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.sim import simulate_encounter
        pack = compile_era("extraction_now")
        trash = next(e for e in pack["enemies"] if e["id"] == "trash")
        cold = simulate_encounter(pack, trash, mode="thermal", heat0=0.0)
        hot = simulate_encounter(pack, trash, mode="thermal", heat0=pack["heat"]["max_heat"] * 0.95)
        assert hot.measured_ttk + 1e-6 >= cold.measured_ttk
        assert hot.heat_end > 0


class TestClosedLoop:
    def test_adapt_ease_on_collapse(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        pack = compile_era("soulslike")
        t = ContextTensor.from_era("soulslike")
        p1 = BuilderBrain().plan(pack, tensor=t)
        p2 = BuilderBrain().plan(pack, tensor=t, last_walk={
            "extracted": False, "collapsed": True, "t": 900.0, "fights": 4, "hops": 20,
        })
        assert p1.adapt == "none"
        assert p2.adapt == "ease"
        assert p2.extract_late is False
        assert p2.spawn_weapon is True
        assert p1.seed != p2.seed
        p1b = BuilderBrain().plan(pack, tensor=t)
        assert p1.seed == p1b.seed

    def test_adapt_harden_on_easy_extract(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        pack = compile_era("soulslike")
        t = ContextTensor.from_era("soulslike")
        p1 = BuilderBrain().plan(pack, tensor=t)
        p2 = BuilderBrain().plan(pack, tensor=t, last_walk={
            "extracted": True, "collapsed": False, "t": 12.0, "fights": 1, "hops": 3,
        })
        assert p2.adapt == "harden"
        assert p2.enemy_mix["elite"] >= p1.enemy_mix["elite"]
        assert p2.enemy_mix["trash"] >= p1.enemy_mix["trash"]
        assert p1.seed != p2.seed

    def test_pipeline_second_run_mutates_plan(self):
        from skeleton.context.pipeline import GameForgeRun
        gf = GameForgeRun()
        a = gf.execute("soulslike extraction with bonfire rest and estus")
        b = gf.execute("soulslike extraction with bonfire rest and estus")
        assert a["succeeded"] and b["succeeded"]
        assert a["build_plan"]["adapt"] == "none"
        assert b["build_plan"]["adapt"] in {"harden", "tighten", "hold", "ease"}
        if a["sim"]["walk"]["t"] < 0.20 * a["sim"]["collapse_max"] and a["sim"]["walk"]["fights"] <= 1:
            assert b["build_plan"]["adapt"] == "harden"
            assert a["build_plan"]["seed"] != b["build_plan"]["seed"]
        assert gf.jeeves.last_walk and gf.jeeves.last_walk.get("extracted")


class TestAuthoredPlan:
    def test_right_bias_is_the_plan_bias(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex.hemispheres import RightHemisphere, LeftHemisphere
        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        ctx = {"era": "soulslike", "tensor": tensor.as_dict(), "pack_dps": pack["primary_dps"], "pack_ttk": pack.get("ttk")}
        right = RightHemisphere().think("plan soulslike forge mix bias ttk extract", ctx)
        left = LeftHemisphere().think("plan soulslike forge mix bias ttk extract", ctx)
        plan = BuilderBrain().plan(pack, tensor=tensor)
        assert plan.authored == "local"
        assert plan.room_bias in right.tags
        assert plan.enemy_mix["trash"] == int(left.numbers[-3])
        assert plan.enemy_mix["elite"] == int(left.numbers[-2])
        # boss may be pruned by left-veto if thermal span blows collapse
        assert plan.enemy_mix["boss"] <= int(left.numbers[-1])

    def test_echo_right_falls_back_balanced(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import JeevesCortex
        neo = JeevesCortex()
        neo.bind_echo("right")
        pack = compile_era("soulslike")
        plan = BuilderBrain().plan(pack, tensor=ContextTensor.from_era("soulslike"), cortex=neo)
        assert plan.authored == "cortex"
        assert plan.room_bias == "balanced"

    def test_pipeline_forge_is_cortex_authored(self):
        from skeleton.context.pipeline import GameForgeRun
        out = GameForgeRun().execute("cozy wholesome farm")
        assert out["succeeded"]
        assert out["build_plan"]["authored"] == "cortex"

    def test_injected_left_changes_mix_keeps_right_bias(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import CallableBackend, JeevesCortex, ttk_oracle
        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        local = BuilderBrain().plan(pack, tensor=tensor)
        neo = JeevesCortex()
        neo.bind("left", CallableBackend(ttk_oracle, slot="left", name="ttk-oracle"))
        inj = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
        assert inj.authored == "cortex"
        assert inj.room_bias == local.room_bias
        assert inj.enemy_mix != local.enemy_mix
        assert inj.enemy_mix["boss"] == 0
        assert inj.enemy_mix["trash"] >= local.enemy_mix["trash"]

    def test_surpass_keeps_oracle_mix_after_rebind(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import CallableBackend, JeevesCortex, ttk_oracle
        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        neo = JeevesCortex()
        neo.bind("left", CallableBackend(ttk_oracle, slot="left", name="ttk-oracle"))
        first = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
        neo.acquire("left")
        neo.surpass("left")
        neo.bind_local("left")
        second = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
        assert second.authored == "own"
        assert second.enemy_mix["trash"] == first.enemy_mix["trash"]
        assert second.enemy_mix["elite"] == first.enemy_mix["elite"]
        assert second.room_bias == first.room_bias


    def test_auto_surpass_authors_mix_without_bind(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import CallableBackend, JeevesCortex, ttk_oracle
        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        local = BuilderBrain().plan(pack, tensor=tensor)
        neo = JeevesCortex()
        neo.bind("left", CallableBackend(ttk_oracle, slot="left", name="ttk-oracle"))
        oracle_mix = None
        saw_own = False
        for _ in range(8):
            p = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
            if oracle_mix is None:
                oracle_mix = dict(p.enemy_mix)
            if p.authored == "own":
                saw_own = True
                break
        assert saw_own, neo.shadow
        neo.bind_local("left")
        assert neo.backends()["left"] != "ttk-oracle"
        after = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
        assert after.authored == "own"
        assert after.enemy_mix == oracle_mix
        assert after.enemy_mix != local.enemy_mix
        assert after.room_bias == local.room_bias


class TestProjectorAndIntake:
    def test_write_and_intake_run(self, tmp_path=None):
        import tempfile, os
        from pathlib import Path as P
        from skeleton.context.questionnaire import intake
        from skeleton.context.pipeline import GameForgeRun
        taken = intake({
            "pace": "processional", "death": "everything", "combat": "earned",
            "info": "nothing", "loot": "build", "heat": "stamina",
            "author": "mine", "social": "solo", "space": "dungeon",
            "fail_state": "bonfire", "ai": "silent", "era_explicit": "soulslike",
        })
        assert taken.era == "soulslike"
        root = tempfile.mkdtemp(prefix="forge-")
        out = GameForgeRun().execute(
            "",
            answers={
                "pace": "processional", "death": "everything", "combat": "earned",
                "info": "nothing", "loot": "build", "heat": "stamina",
                "author": "mine", "social": "solo", "space": "dungeon",
                "fail_state": "bonfire", "ai": "silent", "era_explicit": "soulslike",
            },
            project_root=root,
            overwrite=True,
            target="godot",
        )
        assert out["succeeded"]
        assert out["complete"]
        assert out["era"] == "soulslike"
        assert out["sim"]["passed"] is True
        assert out["sim"]["walk"]["extracted"] is True
        assert out["cortex_observe"]["own_size"] >= 1
        godot = P(root) / "project.godot"
        assert godot.is_file()
        text = godot.read_text()
        assert "HeatSystem=" in text
        enemy = (P(root) / "scripts/combat/enemy.gd").read_text()
        assert "hp_table" in enemy
        assert (P(root) / "FORGE_MANIFEST.json").is_file()


class TestGdScriptCheck:
    def test_closed_graph(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.godot_emit import emit_godot
        from skeleton.forge.gdscript_check import check_ok
        files = emit_godot(compile_era("horror_survival"), title="HORROR")
        ok, problems = check_ok(files)
        assert ok, problems
        assert "scenes/player.tscn" in files
        assert "scenes/extract.tscn" in files
        tscn = files["scenes/levels/run_level.tscn"]
        assert "Room_r00" in tscn
        assert "instance=ExtResource" in tscn
        assert "scripts/world/world_map.gd" in files

    def test_broken_autoload_detected(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.godot_emit import emit_godot
        from skeleton.forge.gdscript_check import check_files
        files = emit_godot(compile_era("extraction_now"))
        del files["scripts/autoloads/heat_system.gd"]
        problems = check_files(files)
        assert any("heat_system" in p for p in problems)


class TestCLI:
    def test_eras_and_run(self):
        from skeleton.__main__ import main
        assert main(["eras"]) == 0
        import tempfile
        root = tempfile.mkdtemp(prefix="cli-")
        rc = main(["run", "silent hill ammo scarce dread", "--out", root, "--overwrite", "--json"])
        assert rc == 0

    def test_plan_and_cockpit(self):
        from skeleton.__main__ import main
        assert main(["plan", "quake rocket jump gib"]) == 0
        assert main(["cockpit", "BLEND ERA cozy_wholesome horror_survival 0.25"]) == 0
        assert main(["walk", "--era", "extraction_now"]) == 0


class TestBlend:
    def test_midpoint_speed(self):
        from skeleton.forge.eras import blend_eras, compile_era
        a = compile_era("arcade_golden_age")
        b = compile_era("soulslike")
        m = blend_eras("arcade_golden_age", "soulslike", 0.5)
        assert m["blend"]["t"] == 0.5
        mid = (a["player"]["speed"] + b["player"]["speed"]) / 2
        assert abs(m["player"]["speed"] - mid) < 1e-6
        trash = next(e for e in m["enemies"] if e["id"] == "trash")
        assert trash["hp"] == round(m["primary_dps"] * trash["ttk_target"], 1)

    def test_pipeline_blend_run(self):
        from skeleton.context.pipeline import GameForgeRun
        out = GameForgeRun().execute("", blend=("arcade_golden_age", "soulslike", 0.5))
        assert out["succeeded"]
        assert "~" in out["era"]
        assert out["sim"]["passed"] is True
        chunk = out["files"]["scripts/player/player_controller.gd"].split("speed: float = ", 1)[1]
        speed = float(chunk.splitlines()[0])
        assert 155.0 < speed < 160.0  # 160 vs 155 midpoint 157.5

    def test_cockpit_blend_drives_detect(self):
        from skeleton.context.cockpit import Cockpit
        from skeleton.context.pipeline import GameForgeRun
        c = Cockpit()
        c.apply("BLEND ERA arcade_golden_age soulslike 0.5")
        c.apply("ROLL ORACLE")
        out = GameForgeRun(cockpit=c).execute("")
        assert out["succeeded"]
        assert "~" in out["era"]
        assert out["build_plan"]["seed"]


class TestWorld:
    def test_connected_and_emitted(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.world import generate_rooms, assert_connected
        from skeleton.forge.godot_emit import emit_godot
        pack = compile_era("metroidvania")
        g = generate_rooms(pack)
        assert_connected(g)
        assert g["rooms"][0]["kind"] == "spawn"
        assert g["rooms"][-1]["kind"] == "extract"
        files = emit_godot(pack)
        assert "data/rooms.json" in files
        import json
        graph = json.loads(files["data/rooms.json"])
        assert_connected(graph)
        tscn = files["scenes/levels/run_level.tscn"]
        for room in graph["rooms"]:
            assert f'name="Room_{room["id"]}"' in tscn
        assert "Player" in tscn
        assert "Extract" in tscn
        assert graph["rooms"][0]["occupants"][0]["kind"] == "player"
        assert any(o["kind"] == "extract" for o in graph["rooms"][-1]["occupants"])
        from skeleton.forge.world import assert_occupancy
        assert_occupancy(graph)
        assert len(graph["doors"]) == 2 * len(graph["edges"])
        assert 'instance=ExtResource("7")' in tscn
        assert "dest_room" in tscn
        assert "data/hardware.json" in files
        assert "KEY_A" in files["scripts/autoloads/input_bind.gd"]
        assert "Camera2D" in files["scenes/player.tscn"]
        assert "enter_room" in files["scripts/autoloads/game_state.gd"]
        assert "can_enter" in files["scripts/autoloads/game_state.gd"]
        assert "can_enter(dest_room)" in files["scripts/world/door.gd"]


class TestHardware:
    def test_catalog_and_aliases(self):
        from skeleton.forge.hardware import catalog, get_generation, list_generations, detect_generation
        rows = catalog()
        keys = [e["key"] for e in rows]
        assert keys == ["8bit", "16bit", "early3d", "64bit", "earlyhd", "modern", "nextgen"]
        assert [e["order"] for e in rows] == sorted(e["order"] for e in rows)
        assert get_generation("NES")["key"] == "8bit"
        assert get_generation("PS5")["key"] == "modern"
        assert get_generation("garbage")["key"] == "modern"
        ng = get_generation("nextgen")
        assert ng["storage_bytes"][0] >= 250 * 1024**3
        assert ng["asset_capacity"] == round(4_000_000 * 1.4)
        assert get_generation("8bit")["max_poly"] == 0
        assert list_generations() == keys
        era, scores = detect_generation("a nes chiptune metroidvania on famicom")
        assert era == "8bit"
        assert scores["8bit"] >= 2

    def test_pack_stamps_and_emit_viewport(self):
        from skeleton.forge.eras import compile_era
        from skeleton.forge.godot_emit import emit_godot
        pack = compile_era("soulslike", generation="8bit")
        assert pack["hardware"]["key"] == "8bit"
        assert pack["hardware"]["sfx_format"] == "nsf"
        assert pack["hardware"]["pixel_snap"] is True
        files = emit_godot(pack)
        godot = files["project.godot"]
        assert "viewport_width=256" in godot
        assert "viewport_height=240" in godot
        assert "InputBind=" in godot
        assert "#f83800" in files["data/hardware.json"] or "f83800" in files["data/hardware.json"]

    def test_pipeline_generation(self):
        from skeleton.context.pipeline import GameForgeRun
        out = GameForgeRun().execute("nes soulslike bonfire estus", generation="8bit")
        assert out["succeeded"]
        assert out["generation"] == "8bit"
        assert "viewport_width=256" in out["files"]["project.godot"]
        assert out["files"]["scripts/autoloads/game_state.gd"].count("8bit") >= 1

    def test_cli_generations(self):
        from skeleton.__main__ import main
        assert main(["generations"]) == 0
        assert main(["cockpit", "BIND GENERATION snes"]) == 0


class TestLive:
    def test_two_live_runs_share_own(self):
        import os
        import tempfile
        from pathlib import Path
        from skeleton.cortex.live import reset_live, live_cortex
        from skeleton.context.pipeline import GameForgeRun
        os.environ["SKELETON_OWN"] = str(Path(tempfile.mkdtemp()) / "own.json")
        reset_live(wipe_disk=True)
        a = GameForgeRun.live()
        out = a.execute("cozy wholesome farm")
        assert out["succeeded"]
        size1 = live_cortex().own.size
        assert size1 > 0
        b = GameForgeRun.live()
        assert b.jeeves.cortex is a.jeeves.cortex
        b.execute("soulslike extraction bonfire estus")
        assert live_cortex().own.size > size1

    def test_disk_survives_process_reset(self):
        import os
        import tempfile
        from pathlib import Path
        from skeleton.cortex.live import reset_live, live_cortex, persist, own_path
        from skeleton.context.pipeline import GameForgeRun
        os.environ["SKELETON_OWN"] = str(Path(tempfile.mkdtemp()) / "own.json")
        reset_live(wipe_disk=True)
        GameForgeRun.live().execute("cozy wholesome farm")
        persist()
        size = live_cortex().own.size
        assert own_path().exists()
        reset_live()
        assert live_cortex().own.size == size

    def test_isolated_run_does_not_touch_live(self):
        import os
        import tempfile
        from pathlib import Path
        from skeleton.cortex.live import reset_live, live_cortex
        from skeleton.context.pipeline import GameForgeRun
        os.environ["SKELETON_OWN"] = str(Path(tempfile.mkdtemp()) / "own.json")
        reset_live(wipe_disk=True)
        live_cortex()
        size = live_cortex().own.size
        GameForgeRun().execute("cozy wholesome farm")
        assert live_cortex().own.size == size

    def test_train_then_run_is_same_jeeves(self):
        import os
        import tempfile
        from pathlib import Path
        from skeleton.cortex.live import reset_live, live_cortex, persist
        from skeleton.context.pipeline import GameForgeRun
        os.environ["SKELETON_OWN"] = str(Path(tempfile.mkdtemp()) / "own.json")
        reset_live(wipe_disk=True)
        live_cortex().train(epochs=1)
        persist()
        size = live_cortex().own.size
        assert size > 0
        out = GameForgeRun.live().execute("soulslike extraction bonfire estus")
        assert out["succeeded"]
        assert live_cortex().own.size >= size
        assert out["build_plan"]["authored"] in {"cortex", "own"}
        assert out.get("own", {}).get("own") == live_cortex().own.size


class TestHive:
    def test_tract_from_a_authors_mix_on_b(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import CallableBackend, JeevesCortex, ttk_oracle
        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        a = JeevesCortex()
        a.bind("left", CallableBackend(ttk_oracle, slot="left", name="ttk-oracle"))
        plan_a = BuilderBrain().plan(pack, tensor=tensor, cortex=a)
        a.acquire("left")
        tract = a.export_tract("left")
        assert tract["size"] >= 1
        assert any(len(e.get("numbers") or []) >= 3 for e in tract["exemplars"])
        b = JeevesCortex()
        got = b.import_tract(tract)
        assert got["copied"] >= 1
        b.surpass("left")
        plan_b = BuilderBrain().plan(pack, tensor=tensor, cortex=b)
        assert plan_b.authored == "own"
        assert plan_b.enemy_mix == plan_a.enemy_mix
        assert plan_b.room_bias == plan_a.room_bias
        local = BuilderBrain().plan(pack, tensor=tensor)
        assert plan_b.enemy_mix != local.enemy_mix


class TestImprove:
    def test_own_mix_beats_teacher_slack(self):
        from dataclasses import replace
        from skeleton.forge.eras import compile_era
        from skeleton.forge.walk import walk_from_pack
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.jeeves.core import Jeeves
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import JeevesCortex

        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        collapse = float(pack["session"]["collapse_max"])
        base = BuilderBrain().plan(pack, tensor=tensor)
        easy = replace(base, enemy_mix={"trash": 1, "elite": 0, "boss": 0})
        hard = replace(base, enemy_mix={"trash": 6, "elite": 2, "boss": 0})

        def slack(plan):
            wr = walk_from_pack(pack, plan=plan.to_dict(), mode="thermal")
            d = wr.to_dict()
            d["collapse_max"] = collapse
            s = ((collapse - wr.t) / collapse) if wr.extracted and wr.t > 0 else 0.0
            return s, d

        s_easy, w_easy = slack(easy)
        s_hard, w_hard = slack(hard)
        assert s_easy > s_hard, (s_easy, s_hard)

        neo = JeevesCortex()
        neo.auto_surpass = False
        j = Jeeves()
        j.cortex = neo
        j.observe_run(era="soulslike", walk=w_hard, plan=hard.to_dict())
        j.observe_run(era="soulslike", walk=w_easy, plan=easy.to_dict())
        neo.surpass("left")
        own = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
        wr_own = walk_from_pack(pack, plan=own.to_dict(), mode="thermal")
        s_own = ((collapse - wr_own.t) / collapse) if wr_own.extracted and wr_own.t > 0 else 0.0
        assert own.authored == "own", own.authored
        assert own.enemy_mix == {"trash": 1, "elite": 0, "boss": 0}, own.enemy_mix
        assert s_own > s_hard, (s_own, s_hard, wr_own.t, wr_own.extracted)

    def test_invents_unobserved_neighbor(self):
        from dataclasses import replace
        from skeleton.forge.eras import compile_era
        from skeleton.forge.walk import walk_from_pack
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.jeeves.core import Jeeves
        from skeleton.context.tensor import ContextTensor
        from skeleton.cortex import JeevesCortex

        pack = compile_era("soulslike")
        tensor = ContextTensor.from_era("soulslike")
        collapse = float(pack["session"]["collapse_max"])
        base = BuilderBrain().plan(pack, tensor=tensor)
        hard = replace(base, enemy_mix={"trash": 6, "elite": 2, "boss": 0})
        wr_h = walk_from_pack(pack, plan=hard.to_dict(), mode="thermal")
        w_hard = wr_h.to_dict()
        w_hard["collapse_max"] = collapse
        s_hard = ((collapse - wr_h.t) / collapse) if wr_h.extracted and wr_h.t > 0 else 0.0
        neo = JeevesCortex()
        neo.auto_surpass = False
        j = Jeeves()
        j.cortex = neo
        j.observe_run(era="soulslike", walk=w_hard, plan=hard.to_dict())
        neo.surpass("left")
        own = BuilderBrain().plan(pack, tensor=tensor, cortex=neo)
        got = (own.enemy_mix["trash"], own.enemy_mix["elite"], own.enemy_mix["boss"])
        assert own.authored == "own", own.authored
        assert got != (6, 2, 0), got
        assert any("invented" in n for n in own.notes), own.notes
        wr = walk_from_pack(pack, plan=own.to_dict(), mode="thermal")
        s_own = ((collapse - wr.t) / collapse) if wr.extracted and wr.t > 0 else 0.0
        assert s_own > s_hard, (s_own, s_hard, got)

