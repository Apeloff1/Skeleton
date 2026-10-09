"""Hardware-era practice matrix must never exaggerate supported games."""
from __future__ import annotations
from skeleton.ai.webcrawler.dragon_native_targets import (
    practice_matrix,target_catalog,TARGETS,STYLES,
)
from skeleton.ai.webcrawler.dragon_native_projects import EMITTERS
from skeleton.ai.webcrawler.dragon_native_curriculum import MILESTONES

def test_matrix_accurately_counts_source_emitters_per_style():
    rows=practice_matrix()
    catalog=target_catalog()
    assert len(rows)==len(STYLES)
    assert len(catalog)==len(TARGETS)
    assert len(EMITTERS)==57
    for row in rows:
        style=row["style"]
        correct=tuple(t["id"] for t in catalog
                      if t["status"]=="native_source" and
                      style in t["supported_styles"])
        assert row["native_emitters"]==correct
        assert row["supported_hardware_count"]==len(correct)
        assert row["catalog_hardware_count"]==len(TARGETS)
        assert row["remaining_adapter_work"]==(len(correct)!=len(TARGETS))
        assert row["coverage_claim"]=="source_supported_not_compiled"
    by_name={entry["style"]:entry for entry in rows}
    assert by_name["arcade_score_attack"]["supported_hardware_count"]==57
    assert "nes" in by_name["arcade_score_attack"]["native_emitters"]
    assert by_name["fixed_screen_puzzle"]["supported_hardware_count"]==25
    assert by_name["first_person_shooter"]["supported_hardware_count"]==25
    assert by_name["rhythm_game"]["supported_hardware_count"]==25
    assert by_name["grand_strategy"]["supported_hardware_count"]==0
    from skeleton.ai.webcrawler.dragon_desktop_abi import DESKTOP_NATIVE
    assert set(by_name["fixed_screen_puzzle"]["native_emitters"])==DESKTOP_NATIVE

def test_adaptive_curriculum_teaches_real_new_hardware_and_native_puzzles():
    curr={step.milestone_id:step for step in MILESTONES}
    assert len(curr)==len(MILESTONES)
    for mid,target,style in (
        ("n64_joystick","nintendo_64","arcade_score_attack"),
        ("nds_dual","nintendo_ds","arcade_score_attack"),
        ("psp_analog","psp","arcade_score_attack"),
        ("desktop_logic","pc_linux","fixed_screen_puzzle"),
    ):
        stage=curr[mid]
        assert stage.target==target and stage.genre==style
        assert stage.requires==("nes","game_boy_color")
        assert stage.weight>0
    assert all(step.target in EMITTERS for step in MILESTONES)
