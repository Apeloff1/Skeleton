"""Recovered checkpoint and publication truth contracts."""
from copy import deepcopy

import pytest

from gameforge.workflow import autonomous_workflow as workflow
from gameforge.workflow import internal_build_system as builds
from gameforge.workflow.workflow_persistence import _without_delivery_credentials


class Store:
    def __init__(self):
        self.state = None
        self.run = None
        self.events = []
        self.fail_save = False

    def save_state(self, project, state):
        self.state = deepcopy(state)
        self.events.append("checkpoint")

    def save_run(self, project, run):
        if self.fail_save:
            raise RuntimeError("save failed")
        self.run = deepcopy(run)
        self.events.append("run")

    def clear_state(self, project):
        self.events.append("clear")
        self.state = None


def test_resume_regenerates_exact_best_and_publishes_before_clear(monkeypatch):
    monkeypatch.setattr(builds, "require_execution_allowed", lambda *_: True)
    store = Store()
    monkeypatch.setattr(workflow, "workflow_persistence", store)
    publications = []
    def publish(self, production, quality, base_url=""):
        publications.append((production["_signature"]["digest"], quality))
        return {"deploy_ready": False}
    monkeypatch.setattr(workflow.WorkflowRun, "deployment_phase", publish)
    run = workflow.WorkflowRun("demo", "small combat adventure", 1)
    store.fail_save = True
    with pytest.raises(RuntimeError, match="save failed"):
        run.execute()
    assert store.state["best_candidate"]["artifact_sha256"] == publications[0][0]
    resumed = workflow.WorkflowRun.from_state(store.state)
    store.fail_save = False
    result = resumed.execute(resume=True)
    assert publications[0] == publications[1]
    assert result["prototype_ready"] and not result["deploy_ready"]
    assert store.events[-2:] == ["run", "clear"]


def test_legacy_checkpoint_cannot_publish_unavailable_artifact():
    run = workflow.WorkflowRun("demo", "combat adventure", 1)
    run.iterations = [{"iteration": 1, "quality": .95}]
    run.quality_history = [.95]
    with pytest.raises(ValueError, match="legacy checkpoint"):
        run.execute(resume=True)


def test_history_strips_bearer_tokens_recursively():
    original = {"deployment": {"package": {"download_token": "secret"},
                "delivery": {"token": "secret", "download_link": "/download?token=secret",
                             "qr_payload": "https://example.test/download?token=secret"}}}
    clean = _without_delivery_credentials(original)
    assert "secret" not in repr(clean)
    assert clean["deployment"]["delivery"]["download_link"] == "/download"
    assert original["deployment"]["delivery"]["token"] == "secret"
