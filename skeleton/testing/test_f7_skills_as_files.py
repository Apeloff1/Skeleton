"""F-7: skills-as-files context architecture (reload task state from disk)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.context.skills_files import (
    ContextCard,
    SkillBank,
    SkillSpec,
    SkillsContextLoop,
    SkillsFilesError,
    TaskState,
    mastery_to_skill_file,
)


def _bank(tmp_path: Path) -> SkillBank:
    return SkillBank(tmp_path / "skills_bank")


def test_upsert_and_reload_skill(tmp_path: Path):
    bank = _bank(tmp_path)
    spec = SkillSpec(
        skill_id="forge.eras",
        description="List era dialects",
        source="manual",
        instructions="Call eras and report DPS/speed.",
    )
    path = bank.upsert_skill(spec)
    assert path.is_file()
    loaded = bank.load_skill("forge.eras")
    assert loaded.skill_id == "forge.eras"
    assert loaded.instructions.startswith("Call eras")
    assert bank.list_skills() == ["forge.eras"]


def test_task_state_roundtrip_and_note_cap(tmp_path: Path):
    bank = _bank(tmp_path)
    bank.upsert_skill(SkillSpec(skill_id="s1", instructions="do the thing"))
    task = TaskState(task_id="t1", skill_id="s1", status="pending")
    for i in range(30):
        task.append_note(f"note-{i} " + ("x" * 300))
    bank.save_task(task)
    loaded = bank.load_task("t1")
    assert len(loaded.notes) == 16  # capped
    assert all(len(n) <= 240 for n in loaded.notes)
    assert loaded.notes[-1].startswith("note-29")


def test_fresh_iteration_reloads_from_disk_not_memory(tmp_path: Path):
    bank = _bank(tmp_path)
    bank.upsert_skill(
        SkillSpec(
            skill_id="walk.prove",
            instructions="Prove spawn→extract.",
            description="walk gate",
        )
    )
    bank.ensure_task("walk-1", "walk.prove")

    # Mutate the on-disk task *outside* the loop to prove reload.
    disk_task = bank.load_task("walk-1")
    disk_task.cursor = "room-spawn"
    disk_task.append_note("seeded-on-disk")
    bank.save_task(disk_task)

    seen: list[str] = []

    def step(card: ContextCard, task: TaskState):
        seen.append(task.cursor)
        assert "seeded-on-disk" in task.notes
        assert card.instructions.startswith("Prove spawn")
        assert card.iteration == task.iteration + 1
        return {"cursor": "room-extract", "note": f"hop-{task.iteration}", "done": True}

    loop = SkillsContextLoop(bank)
    report = loop.iterate("walk-1", step)
    assert report.reloaded_from_disk is True
    assert report.status == "done"
    assert seen == ["room-spawn"]

    # New loop instance (fresh process memory) continues from disk.
    loop2 = SkillsContextLoop(bank)
    reloaded = bank.load_task("walk-1")
    assert reloaded.cursor == "room-extract"
    assert reloaded.iteration == 1
    assert any(n.startswith("hop-") for n in reloaded.notes)
    assert loop2.memory_footprint()["transcript_len"] == 0


def test_context_does_not_grow_across_iterations(tmp_path: Path):
    bank = _bank(tmp_path)
    bank.upsert_skill(
        SkillSpec(
            skill_id="plan.build",
            instructions="Build a short plan.",
        )
    )
    bank.ensure_task("plan-1", "plan.build")

    card_sizes: list[int] = []

    def step(card: ContextCard, task: TaskState):
        card_sizes.append(card.chars)
        # Append a loud note each time — must stay capped on disk / card.
        return {
            "note": ("blob-" + str(task.iteration)) * 40,
            "payload": {"n": task.iteration},
            "done": task.iteration >= 11,
        }

    loop = SkillsContextLoop(bank)
    reports = loop.run("plan-1", step, max_iterations=20)
    assert len(reports) == 12  # iterations 1..12, done when iteration>=11 after step
    # Card size stays bounded (notes_tail capped; instructions fixed).
    assert max(card_sizes) < 8000
    assert max(card_sizes) - min(card_sizes) < 2500
    fp = loop.memory_footprint()
    assert fp["transcript_len"] == 0
    assert fp["working_card_live"] is False
    assert fp["iterations_run"] == 12
    # Only last report retained on the loop object.
    assert loop.last_report is not None
    assert loop.last_report.iteration == reports[-1].iteration


def test_import_gameforge_permanent_bank_shape(tmp_path: Path):
    bank = _bank(tmp_path)
    gf = tmp_path / "skill_bank_jeeves_permanent.json"
    gf.write_text(
        json.dumps(
            {
                "skill_bank_type": "permanent_jeeves",
                "skills": [
                    {
                        "skill_name": "mcp_search",
                        "source": "MCP",
                        "description": "Web search tool",
                        "permanent_for_jeeves": True,
                    },
                    {
                        "skill_id": "room.coherence",
                        "description": "Keep room coherent",
                        "source": "room",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    imported = bank.import_gameforge_bank_file(gf)
    assert "mcp_search" in imported
    assert "room.coherence" in imported
    assert bank.load_skill("mcp_search").source == "MCP"
    assert "Web search" in bank.load_skill("mcp_search").instructions


def test_import_gameforge_per_room_unlocked(tmp_path: Path):
    bank = _bank(tmp_path)
    gf = tmp_path / "skill_bank_per_room.json"
    gf.write_text(
        json.dumps(
            {
                "skill_bank_per_room": {
                    "room_id": "arcade",
                    "unlocked_skills": ["dash", "parry"],
                    "feeds_into_jeeves_permanent_skill_bank": True,
                }
            }
        ),
        encoding="utf-8",
    )
    imported = bank.import_gameforge_bank_file(gf)
    assert imported == ["dash", "parry"]
    assert bank.load_skill("dash").source == "gameforge.room"


def test_mastery_bridge_writes_skill_file(tmp_path: Path):
    bank = _bank(tmp_path)
    spec = mastery_to_skill_file(
        "bloom.apply",
        mastery=0.42,
        confidence=0.7,
        attempts=3,
    )
    bank.upsert_skill(spec)
    loaded = bank.load_skill("bloom.apply")
    assert loaded.source == "assessment.snapshot"
    assert loaded.meta["mastery"] == pytest.approx(0.42)
    assert "mastery=0.4200" in loaded.instructions


def test_task_skill_mismatch_raises(tmp_path: Path):
    bank = _bank(tmp_path)
    bank.upsert_skill(SkillSpec(skill_id="a", instructions="A"))
    bank.upsert_skill(SkillSpec(skill_id="b", instructions="B"))
    bank.save_task(TaskState(task_id="t", skill_id="a"))
    loop = SkillsContextLoop(bank)

    def step(card, task):
        return {"done": True}

    # Task on disk is bound to skill a; requesting skill b must fail closed.
    with pytest.raises(SkillsFilesError, match="mismatch"):
        loop.iterate("t", step, skill_id="b")


def test_invalid_skill_id_rejected(tmp_path: Path):
    bank = _bank(tmp_path)
    with pytest.raises(SkillsFilesError):
        bank.upsert_skill(SkillSpec(skill_id="../etc", instructions="nope"))


def test_missing_skill_file_raises(tmp_path: Path):
    bank = _bank(tmp_path)
    with pytest.raises(SkillsFilesError, match="missing"):
        bank.load_skill("nope")
