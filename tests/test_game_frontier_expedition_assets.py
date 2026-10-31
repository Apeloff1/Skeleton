"""Original procedural 3D terrain, LOD, materials and asset-chain replay."""
from dataclasses import replace
from copy import deepcopy
import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_assets import (
    VisualDesign,forge_expedition_assets,verify_expedition_assets,
)

SOURCE="f"*64


def world():
    return author_archipelago("assets",SOURCE,ArchipelagoProfile(seed=11,islands=5))


def test_assets_have_real_obj_triangulated_geometry_and_three_lod_passes():
    w=world()
    made=forge_expedition_assets(w)
    inventory=made["manifest"]
    assert inventory["count"]==len(w.waypoints)*3
    assert len(made["files"])==inventory["count"]
    assert [x["lod"] for x in inventory["assets"][:3]]==[0,1,2]
    for item in inventory["assets"]:
        mesh=made["files"][item["mesh_path"]]
        assert mesh.startswith("# Original Skeleton game terrain")
        assert sum(line.startswith("v ") for line in mesh.splitlines())>5
        assert sum(line.startswith("f ") for line in mesh.splitlines())==item["triangles"]
        assert "vn " in mesh and "s 1" in mesh
    assert not inventory["native_render_verified"]


def test_asset_digest_rebuild_is_bitwise_reproducible_and_source_bound():
    w=world()
    a=forge_expedition_assets(w)
    assert a==forge_expedition_assets(w)
    proof=verify_expedition_assets(w,VisualDesign(),a)
    assert proof["asset_count"]==a["manifest"]["count"]
    assert len(proof["geometry_receipt"])==64


def test_asset_detail_scalars_change_actual_geometry_or_material_receipt():
    w=world()
    a=forge_expedition_assets(w,VisualDesign(detail_scale=0.1))
    b=forge_expedition_assets(w,VisualDesign(detail_scale=0.8))
    assert a!=b
    filename=next(iter(a["files"]))
    assert a["files"][filename]!=b["files"][filename]
    with pytest.raises(ExpeditionError,match="not reproduced"):
        verify_expedition_assets(w,VisualDesign(detail_scale=0.8),a)


def test_asset_tampering_is_not_accepted_even_if_metadata_untouched():
    w=world()
    correct=forge_expedition_assets(w)
    forged=deepcopy(correct)
    key=next(iter(forged["files"]))
    forged["files"][key]+="\nf 1//1 2//2 3//3\n"
    with pytest.raises(ExpeditionError,match="not reproduced"):
        verify_expedition_assets(w,VisualDesign(),forged)


def test_assets_produce_original_biome_colors_and_site_positions():
    w=world()
    assets=forge_expedition_assets(w)["manifest"]["assets"]
    sky=next(x for x in assets if x["kind"]=="sky_island")
    water=next(x for x in assets if x["kind"]=="underwater")
    assert sky["albedo_rgb"]!=water["albedo_rgb"]
    assert sky["waypoint"] in w.by_id
    assert sky["altitude_m"]==w.by_id[sky["waypoint"]].altitude_m
    assert sky["shadow_strength"]==0.7
    assert sky["foliage_density"]==0.6


def test_asset_budget_fails_before_partial_project_is_published():
    with pytest.raises(ExpeditionError,match="budget exhausted"):
        forge_expedition_assets(world(),max_assets=2)


@pytest.mark.parametrize("parameters",(
    {"radius_m":float("nan")},{"roughness":1.1},
    {"foliage_density":-1},{"seed":True},{"detail_scale":float("inf")},
))
def test_invalid_visual_design_rejected(parameters):
    with pytest.raises(ExpeditionError):
        VisualDesign(**parameters)


def test_lod_must_decrease_and_have_unique_topologies():
    with pytest.raises(ExpeditionError,match="LOD"):
        forge_expedition_assets(world(),lod_segments=(6,24,12))
    with pytest.raises(ExpeditionError,match="LOD"):
        forge_expedition_assets(world(),lod_segments=(24,24,6))
