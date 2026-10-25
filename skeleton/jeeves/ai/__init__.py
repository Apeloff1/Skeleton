"""Jeeves AI control-plane primitives."""
from .contracts import Authority, ContractLedger, ContractRecord, ContractState
from .orchestration import OrchestrLedger, OrchestrRecord, OrchestrState
from .evaluation import EvalLedger, EvalRecord, EvalState

__all__ = [
    "Authority",
    "ContractLedger",
    "ContractRecord",
    "ContractState",
    "OrchestrLedger",
    "OrchestrRecord",
    "OrchestrState",
    "EvalLedger",
    "EvalRecord",
    "EvalState",
    "CreatorRunbook",
    "CreatorRunbookRunner",
    "CreatorRunbookError",
    "CreatorRunbookStep",
    "RunbookState",
    "RunbookStepStatus",
    "CreatorRunbookStore",
    "DurableOrchestrLedger",
    "OrchestrationStoreError",
]


# Host execution adapters are deliberately lazy so importing pure planning
# records never initializes the full agent/tool runtime or storage engines.
from importlib import import_module as _import_module

_HOST_EXPORTS = {
    "CreatorRunbook": ".creator_runbook_runtime",
    "CreatorRunbookRunner": ".creator_runbook_runtime",
    "CreatorRunbookError": ".creator_runbook_runtime",
    "CreatorRunbookStep": ".creator_runbook_runtime",
    "RunbookState": ".creator_runbook_runtime",
    "RunbookStepStatus": ".creator_runbook_runtime",
    "CreatorRunbookStore": ".creator_runbook_store",
    "DurableOrchestrLedger": ".orchestration_store",
    "OrchestrationStoreError": ".orchestration_store",
}


def _load_trusted_lazy_module(module: str):
    """Import from the repository-owned export map using only literal targets."""
    if module == ".creator_runbook_runtime":
        return _import_module(".creator_runbook_runtime", __name__)
    if module == ".creator_runbook_store":
        return _import_module(".creator_runbook_store", __name__)
    if module == ".orchestration_store":
        return _import_module(".orchestration_store", __name__)
    raise ImportError("unregistered lazy export module")



def __getattr__(name: str):
    module = _HOST_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"{__name__!r} has no attribute {name!r}")
    value = getattr(_load_trusted_lazy_module(module), name)
    globals()[name] = value
    return value
