"""F-7: skills-as-files context architecture (reload task state from disk)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.context import skills_files as skills_files_module
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



def test_load_skill_rejects_symlinked_bank_entry(tmp_path: Path):
    bank = _bank(tmp_path)
    victim = tmp_path / "victim.json"
    victim.write_text(
        json.dumps({"skill_id": "safe", "instructions": "outside-bank"}),
        encoding="utf-8",
    )
    target = bank.skill_path("safe")
    try:
        target.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(SkillsFilesError, match="failed to read"):
        bank.load_skill("safe")


def test_load_task_rejects_symlinked_bank_entry(tmp_path: Path):
    bank = _bank(tmp_path)
    victim = tmp_path / "victim-task.json"
    victim.write_text(
        json.dumps({"task_id": "t1", "skill_id": "s1"}),
        encoding="utf-8",
    )
    target = bank.task_path("t1")
    try:
        target.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(SkillsFilesError, match="failed to read"):
        bank.load_task("t1")


def test_atomic_write_does_not_follow_predictable_legacy_temp_symlink(tmp_path: Path):
    bank = _bank(tmp_path)
    target = bank.skill_path("safe")
    victim = tmp_path / "victim.txt"
    victim.write_text("sentinel", encoding="utf-8")
    legacy_tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        legacy_tmp.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")

    bank.upsert_skill(SkillSpec(skill_id="safe", instructions="bounded"))

    assert victim.read_text(encoding="utf-8") == "sentinel"
    assert legacy_tmp.is_symlink()
    assert bank.load_skill("safe").instructions == "bounded"


def test_atomic_write_cleans_unique_temp_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bank = _bank(tmp_path)
    target = bank.skill_path("safe")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(skills_files_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        bank.upsert_skill(SkillSpec(skill_id="safe", instructions="bounded"))

    assert not target.exists()
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_orders_file_sync_replace_and_directory_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bank = _bank(tmp_path)
    events: list[str] = []
    real_replace = skills_files_module.os.replace

    def record_fsync(_fd):
        events.append("file-fsync")

    def record_replace(source, target):
        events.append("replace")
        real_replace(source, target)

    def record_directory_sync(_path):
        events.append("directory-fsync")

    monkeypatch.setattr(skills_files_module.os, "fsync", record_fsync)
    monkeypatch.setattr(skills_files_module.os, "replace", record_replace)
    monkeypatch.setattr(
        skills_files_module,
        "_fsync_parent_directory",
        record_directory_sync,
    )

    bank.upsert_skill(SkillSpec(skill_id="safe", instructions="bounded"))

    assert events == ["file-fsync", "replace", "directory-fsync"]


def test_parent_directory_sync_closes_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    if skills_files_module.os.name == "nt":
        pytest.skip("directory fsync is intentionally skipped on Windows")

    target = tmp_path / "skills" / "safe.json"
    target.parent.mkdir(parents=True)
    events: list[tuple[str, object]] = []
    directory_fd = 991

    def fake_open(path, flags):
        events.append(("open", (Path(path), flags)))
        return directory_fd

    def fake_fsync(fd):
        events.append(("fsync", fd))

    def fake_close(fd):
        events.append(("close", fd))

    monkeypatch.setattr(skills_files_module.os, "open", fake_open)
    monkeypatch.setattr(skills_files_module.os, "fsync", fake_fsync)
    monkeypatch.setattr(skills_files_module.os, "close", fake_close)

    skills_files_module._fsync_parent_directory(target)

    assert events[0][0] == "open"
    assert events[0][1][0] == target.parent
    assert events[1:] == [("fsync", directory_fd), ("close", directory_fd)]


def test_directory_sync_failure_reports_failure_without_claiming_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    bank = _bank(tmp_path)
    target = bank.skill_path("safe")

    def fail_directory_sync(_path):
        raise OSError("directory fsync failed after replace")

    monkeypatch.setattr(
        skills_files_module,
        "_fsync_parent_directory",
        fail_directory_sync,
    )

    with pytest.raises(OSError, match="directory fsync failed after replace"):
        bank.upsert_skill(SkillSpec(skill_id="safe", instructions="bounded"))

    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["skill_id"] == "safe"
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []
