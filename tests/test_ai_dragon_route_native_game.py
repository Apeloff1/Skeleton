"""Compile and actually play the original C99 multi-route free-roam world."""
from __future__ import annotations
from pathlib import Path
import json,shutil,subprocess,pytest

from skeleton.ai.webcrawler.dragon_route_native_game import (
    SCHEMA,EXAMPLES,emit_route_game,
)
from skeleton.ai.webcrawler.dragon_route_world_factory import make_frontier
from skeleton.ai.webcrawler.dragon_route_world import replay


@pytest.mark.parametrize("weather",["clear","rain","windy","high_tide"])
def test_real_world_project_emits_native_c99_transitions_and_exact_python_proofs(weather):
    world,traveller=make_frontier(seed=1977,weather=weather,hour=8)
    files=emit_route_game(world,traveller,authorized=True)
    assert files["src/main.c"].startswith("/* Original world routes")
    assert "step_world" in files["src/main.c"]
    assert "player.acquired" in files["src/main.c"]
    assert "player.clock" in files["src/main.c"]
    assert "player.energy" in files["src/main.c"]
    assert "edge->secret" in files["src/main.c"]
    assert "edge->weather_any" in files["src/main.c"]
    assert "departure_wait(edge)" in files["src/main.c"]
    assert "run_probes" in files["src/main.c"]
    assert "DRAGON_ORIGINAL_WORLD_PASS" in files["src/main.c"]
    header=files["include/dragon_route_world.h"]
    assert "static const DragonConnection dragon_connections" in header
    assert "static const DragonProof dragon_probes" in header
    audit=json.loads(files["dragon-original-route-proof.json"])
    assert audit["schema"]==SCHEMA
    assert audit["source"]=="strictly original generated game-world graph"
    assert audit["abstract_graph_audit"]["places"]==len(world.places)
    assert audit["abstract_graph_audit"]["routes"]==len(world.connections)
    assert len(audit["probes"])>=6
    if weather=="rain":assert any(x["name"]=="rain" for x in audit["probes"])
    if weather=="windy":assert any(x["name"]=="windy" for x in audit["probes"])
    if weather=="high_tide":assert any(x["name"]=="tide" for x in audit["probes"])
    for item in audit["probes"]:
        expected=replay(world,tuple(item["route"]),traveller,
                        objective="native_witness")
        assert item["digest"]==expected.digest
        assert item["elapsed"]==expected.elapsed_minutes
        assert item["spent"]==expected.money_spent
        assert item["danger"]==expected.risk


def test_native_game_export_requires_explicit_original_rights_authorization():
    world,traveller=make_frontier()
    with pytest.raises(PermissionError):
        emit_route_game(world,traveller,authorized=False)


@pytest.mark.skipif(not shutil.which("cc"),reason="native original game requires real C99 compiler")
@pytest.mark.parametrize("weather",["clear","windy","rain","high_tide"])
def test_original_free_roam_game_compiles_and_executes_distinct_true_routes(
    tmp_path,weather,
):
    world,traveller=make_frontier(seed=1977,weather=weather,hour=8)
    files=emit_route_game(world,traveller,authorized=True)
    for filename,content in files.items():
        destination=tmp_path/filename
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(content)
    binary=tmp_path/"dragon_route_game"
    compiled=subprocess.run(
        ["cc","-std=c99","-O2","-Wall","-Wextra","-pedantic",
         "-Werror","-Iinclude","src/main.c","-o",str(binary)],
        cwd=tmp_path,capture_output=True,text=True,timeout=40,
    )
    assert compiled.returncode==0,compiled.stderr
    observed=subprocess.run(
        [str(binary),"--selftest"],cwd=tmp_path,
        capture_output=True,text=True,timeout=20,
    )
    assert observed.returncode==0,(observed.stdout,observed.stderr)
    manifest=json.loads(files["dragon-original-route-proof.json"])
    assert observed.stdout.count("DRAGON_ORIGINAL_ROUTE_PASS name=")==len(
        manifest["probes"])
    assert observed.stdout.strip().endswith(
        f"DRAGON_ORIGINAL_WORLD_PASS probes={len(manifest['probes'])} "
        f"places={len(world.places)} routes={len(world.connections)}"
    )


@pytest.mark.skipif(not shutil.which("cc"),reason="native C99 required")
def test_game_is_interactive_not_only_a_generated_json_husk(tmp_path):
    world,traveller=make_frontier()
    files=emit_route_game(world,traveller,authorized=True)
    for name,body in files.items():
        target=tmp_path/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(body)
    built=subprocess.run(["make"],cwd=tmp_path,
                         capture_output=True,text=True,timeout=35)
    assert built.returncode==0,built.stderr
    played=subprocess.run(
        [str(tmp_path/"dragon_route_game")],cwd=tmp_path,
        input="999\n1\nq\n",capture_output=True,text=True,timeout=10,
    )
    assert played.returncode==0
    assert "ORIGINAL ROUTE WORLD" in played.stdout
    assert "Unknown original route number." in played.stdout
    assert "bazaar" in played.stdout
    assert "citadel" in played.stdout


def test_actual_route_game_source_is_reproducible_and_not_a_claim_of_vehicle_physics():
    world,traveller=make_frontier(seed=711)
    a=emit_route_game(world,traveller,authorized=True)
    b=emit_route_game(world,traveller,authorized=True)
    assert a==b
    assert "no mode-specific physics" in a["dragon-original-route-proof.json"]
    assert "not commercial game data" in a["README.md"]
