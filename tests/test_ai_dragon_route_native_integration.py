"""Native project integration: world routes is actual new desktop game style."""
from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile
import json,shutil,subprocess,pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import (
    render_native_project,digest,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    ProductionRequest,PortableGameDesign,
    plan_production,validate_native_source,
    make_source_release,verify_source_release,
    _render,
)
from skeleton.ai.webcrawler.dragon_native_targets import target_catalog,STYLES

def original_request(target="pc_linux",seed=1977):
    return ProductionRequest(
        title="Original Endless Roads",
        style="world_route_adventure",
        targets=(target,),original_work_attested=True,seed=seed,
        portable_design=PortableGameDesign(
            stages=1,candidates=1,difficulty=4,
            project_notes="Original procedural multimodal travel gameplay",
        ),
    )


def test_actual_world_route_game_style_is_not_falsely_marked_for_all_consoles():
    assert "world_route_adventure" in STYLES
    rows={row["id"]:row for row in target_catalog()}
    for target in ("pc_linux","pc_windows","pc_macos","steam_deck"):
        assert "world_route_adventure" in rows[target]["supported_styles"]
        assert plan_production(original_request(target))[0].state=="source_ready"
    for target in ("game_boy","game_boy_color","nes","genesis","ps1","xbox_original"):
        assert "world_route_adventure" not in rows[target]["supported_styles"]
        assert plan_production(original_request(target))[0].state=="blocked"


@pytest.mark.parametrize("target",["pc_linux","pc_windows","pc_macos","steam_deck"])
def test_real_native_project_generates_runnable_route_world_source_and_truthful_scope(target):
    project=_render(original_request(target),target)
    assert project.target_id==target
    assert project.status=="source_generated"
    assert project.style=="world_route_adventure"
    assert project.files["src/main.c"].startswith("/* Original world routes")
    assert "step_world" in project.files["src/main.c"]
    assert "dragon_connections" in project.files["include/dragon_route_world.h"]
    assert "dragon_route_game" in project.files["Makefile"]
    assert "add_executable(dragon_route_game" in project.files["CMakeLists.txt"]
    manifest=json.loads(project.files["dragon-native-manifest.json"])
    assert manifest["runtime_gameplay_mode"]=="native_original_world_routes"
    assert manifest["campaign_stages"]==1
    witness=json.loads(project.files["dragon-original-route-proof.json"])
    assert witness["schema"]=="skeleton.ai.dragon.original_native_route_game.v1"
    assert witness["abstract_graph_audit"]["routes"]>=60
    assert len(witness["probes"])>=6
    validate_native_source(project)


def test_source_release_custody_includes_exact_original_world_itineraries_and_executable_code():
    req=original_request()
    project=_render(req,"pc_linux")
    package,receipt=make_source_release(project,req)
    audit=verify_source_release(package)
    assert receipt["target"]=="pc_linux"
    assert audit["target"]=="pc_linux"
    assert audit["source_fingerprint"]==project.digest
    with ZipFile(BytesIO(package)) as archive:
        sources=[name for name in archive.namelist() if
                 name.endswith("dragon-original-route-proof.json")]
        assert len(sources)==1
        source=json.loads(archive.read(sources[0]))
        assert source["source"]=="strictly original generated game-world graph"


@pytest.mark.skipif(not shutil.which("cc"),reason="real desktop C99 host compiler required")
def test_normal_native_project_builds_genuine_original_world_game_and_replays_routes(tmp_path):
    project=_render(original_request(),"pc_linux")
    for name,body in project.files.items():
        destination=tmp_path/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(body)
    output=subprocess.run(["make"],cwd=tmp_path,
                          capture_output=True,text=True,timeout=45)
    assert output.returncode==0,output.stderr
    run=subprocess.run([str(tmp_path/"dragon_route_game"),"--selftest"],
                       cwd=tmp_path,capture_output=True,text=True,timeout=40)
    assert run.returncode==0,(run.stdout,run.stderr)
    assert "DRAGON_ORIGINAL_WORLD_PASS probes=" in run.stdout
    assert "DRAGON_ORIGINAL_ROUTE_PASS name=outer_space" in run.stdout
    assert "DRAGON_ORIGINAL_ROUTE_PASS name=secret" in run.stdout


def test_source_generator_is_deterministic_but_varies_original_route_world_seed():
    a=_render(original_request(seed=1),"pc_linux")
    b=_render(original_request(seed=1),"pc_linux")
    c=_render(original_request(seed=2),"pc_linux")
    assert a.digest==b.digest
    assert a.files["dragon-original-route-proof.json"]==b.files[
        "dragon-original-route-proof.json"]
    assert a.digest!=c.digest
