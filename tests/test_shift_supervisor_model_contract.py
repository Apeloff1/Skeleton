from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.secretary import SecretaryBot
from core.shift_supervisor.shift_manager import SMBShiftManager


class RecordingModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_both_agents_use_model_gateway_contract():
    store = InMemoryPlanStore()
    manager_model = RecordingModel({"summary": "m", "tasks": [], "delegation": []})
    secretary_model = RecordingModel({"summary": "s", "tasks": []})

    manager = SMBShiftManager(store=store, model=manager_model)
    secretary = SecretaryBot(store=store, model=secretary_model)

    secretary.enrich_plan({"repo": "Skeleton"})
    manager.refresh_plan(project_context={"repo": "Skeleton"}, research=[{"source": "test"}])

    assert len(secretary_model.calls) == 1
    assert len(manager_model.calls) == 1
    assert secretary_model.calls[0]["system_prompt"]
    assert manager_model.calls[0]["system_prompt"]
    assert secretary_model.calls[0]["user_prompt"]
    assert manager_model.calls[0]["user_prompt"]
