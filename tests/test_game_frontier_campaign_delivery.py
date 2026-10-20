"""Milestone 1-7: deterministic original-campaign delivery checks."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO

import pytest

from skeleton.jeeves.game_frontier_expedition import ExpeditionError
from skeleton.jeeves.game_frontier_campaign_delivery import (
    DeliveryPolicy, compare_campaign_bundles, prepare_campaign_bundle,
    publish_campaign_bundle, restore_campaign_bundle, verify_campaign_bundle,
)

GDD = "a" * 64
WORLD = "b" * 64
FILES = {"project.godot": "config_version=5\n",
         "game/scenes/start.gd": "extends Node\n",
         "game/data/world.json": '{"world":"original"}\n'}


def build(files=FILES, **kw):
    return prepare_campaign_bundle(files, project_id="original_demo",
                                   gdd_digest=GDD, world_digest=WORLD, **kw)


def test_m1_m2_admission_and_real_byte_inventory():
    a = build()
    assert a["report"]["file_count"] == 3
    assert a["report"]["source_bytes"] == sum(len(v.encode()) for v in FILES.values())
    assert a["report"]["journal"][0]["stage"] == "admission"
    assert len(a["report"]["journal"]) == 7
    assert verify_campaign_bundle(a["archive"], a["report"], original_files=FILES)["verified"]


@pytest.mark.parametrize("path", (
    "../evil", "/absolute", "./project.godot", "a//b", "folder\\evil",
    "CON.txt", "folder/LPT1.bin", "folder/a.", "x:alternate", "a\nb",
))
def test_m1_rejects_untrusted_paths(path):
    with pytest.raises(ExpeditionError):
        build({path: "payload"})


def test_m1_no_case_insensitive_collision_or_non_utf8():
    with pytest.raises(ExpeditionError, match="collision"):
        build({"A/B.txt": "a", "a/b.TXT": "b"})
    with pytest.raises(ExpeditionError, match="encoding"):
        build({"bad.txt": "\ud800"})
    with pytest.raises(ExpeditionError, match="budget"):
        build({"big": "x"*128}, policy=DeliveryPolicy(max_file_bytes=64))


def test_m3_archive_is_reproducible_in_input_insertion_order():
    a = build(FILES)
    b = build(dict(reversed(list(FILES.items()))))
    assert a == b
    with ZipFile(BytesIO(a["archive"])) as z:
        assert z.namelist() == sorted(FILES)
        assert all(i.compress_type == 0 and i.date_time == (1980, 1, 1, 0, 0, 0)
                   for i in z.infolist())


def test_m4_byte_integrity_tamper_and_forged_receipt_rejected():
    p = build()
    changed = bytearray(p["archive"])
    changed[60] ^= 1
    with pytest.raises(ExpeditionError):
        verify_campaign_bundle(bytes(changed), p["report"])
    copy = deepcopy(p["report"])
    copy["native_gameplay_attested"] = True
    with pytest.raises(ExpeditionError):
        verify_campaign_bundle(p["archive"], copy)
    copy = deepcopy(p["report"])
    copy["files"][0]["sha256"] = "0"*64
    with pytest.raises(ExpeditionError):
        verify_campaign_bundle(p["archive"], copy)
    with pytest.raises(ExpeditionError, match="canonical source"):
        verify_campaign_bundle(p["archive"], p["report"],
                               original_files={"project.godot": "forged"})


def test_m5_disk_restore_and_no_overwrite(tmp_path):
    p = build()
    output = tmp_path / "restored"
    result = restore_campaign_bundle(p["archive"], p["report"], output)
    assert result["restored"]
    for name, data in FILES.items():
        assert (output / name).read_text() == data
    with pytest.raises(ExpeditionError, match="existing destination"):
        restore_campaign_bundle(p["archive"], p["report"], output)


def test_m6_delta_comparison_and_cross_gdd_rejection():
    base = build()
    altered = dict(FILES)
    altered.pop("game/data/world.json")
    altered["game/scenes/start.gd"] = "extends Node2D\n"
    altered["extra.txt"] = "new"
    nxt = build(altered)
    diff = compare_campaign_bundles(base["report"], nxt["report"])
    assert diff["added"] == ["extra.txt"]
    assert diff["removed"] == ["game/data/world.json"]
    assert diff["modified"] == ["game/scenes/start.gd"]
    assert diff["unchanged"] == 1
    assert diff["requires_explicit_migration"]
    foreign = prepare_campaign_bundle(FILES, project_id="original_demo",
                                      gdd_digest="c"*64, world_digest=WORLD)
    with pytest.raises(ExpeditionError, match="canonical GDD"):
        compare_campaign_bundles(base["report"], foreign["report"])


def test_m7_publish_refuses_overwrite_and_signoff(tmp_path):
    p = build()
    assert not p["report"]["production_release_approved"]
    assert not p["report"]["copyright_cleared"]
    assert not p["report"]["native_gameplay_attested"]
    name = tmp_path / "campaign.zip"
    publish_campaign_bundle(p["archive"], name)
    assert name.read_bytes() == p["archive"]
    with pytest.raises(ExpeditionError, match="overwrite"):
        publish_campaign_bundle(p["archive"], name)


def test_source_budget_policy_is_exact_and_bool_rejected():
    with pytest.raises(ExpeditionError):
        DeliveryPolicy(max_files=True)
    with pytest.raises(ExpeditionError):
        DeliveryPolicy(max_file_bytes=128, max_total_bytes=64)
    with pytest.raises(ExpeditionError, match="type"):
        prepare_campaign_bundle(FILES, project_id="original_demo", gdd_digest=GDD,
                                world_digest=WORLD, policy=None)
