"""F-7: skills-as-files fresh-context execution."""
from __future__ import annotations

import json

import pytest

from skeleton.skills.context import (
    ConcurrentTaskUpdate,
    FreshSkillContextLoop,
    SkillContextError,
    TaskFileStore,
    TaskState,
)
from skeleton.skills.manifest import SkillManifest, SkillState
from skeleton.skills.store import SkillStore


def _store(tmp_path):
    store = SkillStore(tmp_path / ".skills")
    manifest = SkillManifest(
        name="repair",
        version="2.1.0",
        capabilities=["inspect", "patch"],
        preconditions=["repository readable"],
        invariants=["read before write", "bounded context"],
        evaluation=["tests pass"],
        provenance="f7-test",
    )
    state = SkillState(status="promoted", attempts=5, successes=5)
    store.save(manifest, state)
    return store


def test_iteration_reloads_manifest_and_task_from_disk(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    loop = FreshSkillContextLoop(store, tasks)
    seen = []

    def first(card, task):
        seen.append((card.skill["version"], card.task["cursor"], card.source_fingerprints))
        return {"cursor": "after-first", "note": "one"}

    r1 = loop.iterate("job-1", first, skill_name="repair")
    assert r1.reloaded_from_disk is True

    # External edits between iterations must become the next context; no stale
    # in-process manifest/task object is authoritative.
    manifest, skill_state = store.load("repair")
    manifest.version = "2.2.0"
    store.save(manifest, skill_state)
    task = tasks.load("job-1")
    task.cursor = "external-cursor"
    tasks.save(task, expected_revision=task.revision)

    def second(card, task):
        seen.append((card.skill["version"], card.task["cursor"], card.source_fingerprints))
        return {"done": True}

    r2 = loop.iterate("job-1", second)
    assert r2.status == "done"
    assert seen[0][0:2] == ("2.1.0", "")
    assert seen[1][0:2] == ("2.2.0", "external-cursor")
    assert seen[0][2] != seen[1][2]


def test_loop_does_not_accumulate_context_transcript(tmp_path):
    store = _store(tmp_path)
    loop = FreshSkillContextLoop(store)

    reports = loop.run(
        "job-2",
        lambda card, task: {"done": task.iteration >= 5, "note": f"step-{task.iteration}"},
        skill_name="repair",
        max_iterations=8,
    )
    assert len(reports) == 6
    footprint = loop.memory_footprint()
    assert footprint["iterations_run"] == 6
    assert footprint["working_card_live"] is False
    assert footprint["transcript_len"] == 0
    assert loop.last_report == reports[-1]


def test_context_card_uses_current_skill_state(tmp_path):
    store = _store(tmp_path)
    loop = FreshSkillContextLoop(store)
    seen = []

    loop.iterate(
        "job-state",
        lambda card, task: seen.append(dict(card.skill_state)) or {},
        skill_name="repair",
    )
    manifest, state = store.load("repair")
    state.record(False, "regression-1")
    store.save(manifest, state)
    loop.iterate("job-state", lambda card, task: seen.append(dict(card.skill_state)) or {"done": True})

    assert seen[0]["attempts"] == 5
    assert seen[0]["regressions"] == 0
    assert seen[1]["attempts"] == 6
    assert seen[1]["regressions"] == 1
    assert seen[1]["last_trace"] == "regression-1"


def test_task_bounds_notes_cursor_and_payload(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    task = TaskState(
        task_id="bounded",
        skill_name="repair",
        cursor="c" * 5000,
        notes=["n" * 1000 for _ in range(40)],
        payload={f"k{i:03d}": "x" * 5000 for i in range(100)},
    )
    tasks.save(task)
    loaded = tasks.load("bounded")

    assert len(loaded.cursor) == 500
    assert len(loaded.notes) == 16
    assert all(len(note) <= 240 for note in loaded.notes)
    assert len(loaded.payload) == 64
    assert all(len(value) <= 1000 for value in loaded.payload.values())


def test_path_traversal_ids_are_rejected(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    with pytest.raises(SkillContextError):
        tasks.path("../escape")
    with pytest.raises(SkillContextError):
        TaskState(task_id="ok", skill_name="../../repair")


def test_existing_task_cannot_be_rebound_to_another_skill(tmp_path):
    store = _store(tmp_path)
    store.save(SkillManifest(name="other"), SkillState())
    tasks = TaskFileStore(store)
    tasks.ensure("job-bind", "repair")
    with pytest.raises(SkillContextError):
        tasks.ensure("job-bind", "other")


def test_optimistic_revision_rejects_lost_update(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    original = tasks.ensure("job-cas", "repair")
    writer_a = tasks.load("job-cas")
    writer_b = tasks.load("job-cas")
    assert writer_a.revision == original.revision == writer_b.revision

    writer_a.cursor = "a"
    tasks.save(writer_a, expected_revision=writer_a.revision)
    writer_b.cursor = "b"
    with pytest.raises(ConcurrentTaskUpdate):
        tasks.save(writer_b, expected_revision=writer_b.revision)
    assert tasks.load("job-cas").cursor == "a"


def test_step_callback_cannot_silently_clobber_concurrent_task_update(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    loop = FreshSkillContextLoop(store, tasks)

    def racing_step(card, task):
        external = tasks.load(task.task_id)
        external.cursor = "external-won"
        tasks.save(external, expected_revision=external.revision)
        return {"cursor": "stale-callback"}

    with pytest.raises(ConcurrentTaskUpdate):
        loop.iterate("job-race", racing_step, skill_name="repair")
    assert tasks.load("job-race").cursor == "external-won"
    assert loop.memory_footprint()["working_card_live"] is False


def test_run_stops_on_terminal_status(tmp_path):
    store = _store(tmp_path)
    loop = FreshSkillContextLoop(store)

    reports = loop.run(
        "job-done",
        lambda card, task: {"done": task.iteration == 2},
        skill_name="repair",
        max_iterations=20,
    )
    assert [r.iteration for r in reports] == [1, 2, 3]
    assert reports[-1].status == "done"


def test_invalid_callback_result_does_not_persist_partial_iteration(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    loop = FreshSkillContextLoop(store, tasks)

    with pytest.raises(SkillContextError):
        loop.iterate("job-bad-return", lambda card, task: ["not", "a", "mapping"], skill_name="repair")
    loaded = tasks.load("job-bad-return")
    assert loaded.iteration == 0
    assert loaded.status == "pending"
    assert loop.memory_footprint()["working_card_live"] is False


def test_task_files_are_plain_json_restartable_state(tmp_path):
    store = _store(tmp_path)
    tasks = TaskFileStore(store)
    loop = FreshSkillContextLoop(store, tasks)
    loop.iterate("job-json", lambda card, task: {"cursor": "phase-2", "payload": {"count": 3}}, skill_name="repair")

    raw = json.loads(tasks.path("job-json").read_text(encoding="utf-8"))
    assert raw["skill_name"] == "repair"
    assert raw["cursor"] == "phase-2"
    assert raw["payload"]["count"] == 3

    # A brand-new loop instance reconstructs solely from the persisted files.
    restarted = FreshSkillContextLoop(SkillStore(store.root))
    report = restarted.iterate("job-json", lambda card, task: {"done": card.task["cursor"] == "phase-2"})
    assert report.status == "done"
    assert report.iteration == 2
