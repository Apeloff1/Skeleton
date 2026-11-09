"""A failed task does not unlock what follows, and a handoff needs an artefact."""

import pytest

from skeleton.swarm.dag import SwarmDag, TaskStatus
from skeleton.swarm.handoff import HandoffError, HandoffRegistry


def test_a_failed_task_blocks_what_depends_on_it() -> None:
    graph = SwarmDag()
    graph.submit("fetch", "read", {"q": "docs"})
    graph.submit("cite", "write", {"q": "docs"}, deps=["fetch"])
    graph.submit("file", "write", {"q": "docs"}, deps=["cite"])
    wave = graph.ready_wave()
    wave[0].status = TaskStatus.DONE
    assert graph.get("fetch").status is TaskStatus.READY
    assert graph.claim("fetch", "ada") is not None
    assert graph.complete("fetch", False) is False
    assert graph.fail("fetch") is True
    assert graph.get("cite").status is TaskStatus.BLOCKED
    assert graph.get("file").status is TaskStatus.BLOCKED
    assert graph.ready_wave() == []


def test_a_handoff_cannot_complete_without_an_artefact() -> None:
    registry = HandoffRegistry(clock=lambda: 10.0)
    task = registry.submit("search", {"q": "docs"}, requester="ada")
    registry.accept(task.task_id, assignee="bea")
    with pytest.raises(HandoffError):
        registry.complete(task.task_id)
    with pytest.raises(HandoffError):
        registry.complete(task.task_id, artefacts=[{"note": "no id"}])
    done = registry.complete(task.task_id, artefacts=[{"id": "cite-1"}])
    assert done.state.value == "completed"
    assert done.artefacts[0]["id"] == "cite-1"
    with pytest.raises(HandoffError):
        registry.fail(task.task_id, "")
