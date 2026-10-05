"""Construct Forge & Material Forge — engine + CRUD + vault + snowball."""
from core import construct_forge as cf


def test_presets_per_era_min_300():
    assert cf.presets_per_era("construct") >= 300
    assert cf.presets_per_era("material") >= 300


def test_list_presets_has_geometry_and_palette():
    for kind in ("construct", "material"):
        d = cf.list_presets(kind, "8bit", 0, 5)
        assert d["per_era"] >= 300
        assert d["kind"] == kind and d["era"] == "8bit"
        p = d["presets"][0]
        assert p["geometry"] and isinstance(p["geometry"], list)
        assert p["palette"] and all(c.startswith("#") for c in p["palette"])


def test_generate_deterministic_no_llm():
    a = cf.generate("construct", "16bit", category="castle", seed=7)
    b = cf.generate("construct", "16bit", category="castle", seed=7)
    assert a["preset_id"] == b["preset_id"]
    assert a["llm_enriched"] is False
    assert a["category"] == "castle"


def test_save_edit_get_delete():
    spec = cf.generate("construct", "modern", category="tower", seed=3)
    res = cf.save_construct(dict(spec))
    cid = res["construct_id"]
    assert cf.get_construct(cid)["construct_id"] == cid
    upd = cf.update_construct(cid, {"name": "Edited", "palette": ["#ff0000"]})
    assert upd["name"] == "Edited" and upd["palette"] == ["#ff0000"]
    assert cf.delete_construct(cid) is True
    assert cf.get_construct(cid) is None


def test_mount_extract_vault():
    spec = cf.generate("material", "modern", category="marble", seed=9)
    cid = cf.save_construct(dict(spec))["construct_id"]
    m = cf.mount_to_build([cid], "ut_build_cf")
    assert m["mounted"] >= 1
    gf = cf.save_to_gamefiles("ut_build_cf", [cid])
    assert gf["gamefiles"] >= 1
    ex = cf.extract_from_build("ut_build_cf")
    assert ex["extracted"] >= 1
    cf.delete_construct(cid)


def test_snowball_forge_for_build():
    r = cf.forge_for_build("ut_snowball_cf", era="early3d", seed=2,
                           construct_count=5, material_count=5, mount=True)
    assert r["constructs"] == 5 and r["materials"] == 5
    assert r["mounted"] is True
    assert r["presets_available"]["construct"] >= 300


def test_capacity_shape():
    c = cf.count()
    assert c["capacity"] == 100_000
    assert "construct" in c and "material" in c
