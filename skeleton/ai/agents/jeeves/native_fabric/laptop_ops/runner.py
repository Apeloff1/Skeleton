"""Allowlisted domain dispatcher with deterministic all-stages-required results."""
from __future__ import annotations
import importlib
from .contracts import LaptopGateHold, DomainVerdict, fingerprint, name

DOMAINS = frozenset((
    "bootstrap", "model_manifest", "tokenizer_identity", "memory_capacity",
    "cpu_admission", "gpu_admission", "context_window", "native_session",
    "generation_budget", "output_receipt", "sqlite_replay", "signed_sources",
    "source_retrieval", "tool_grants", "memory_consent", "pressure_recovery",
    "cancellation", "cold_restart", "first_turn", "release_gates",
))


# Literal-only lazy registry table: never derive an import path from caller input.
_REGISTRY_LOADERS = {
    "bootstrap": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.bootstrap.registry"),
    "model_manifest": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.model_manifest.registry"),
    "tokenizer_identity": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.tokenizer_identity.registry"),
    "memory_capacity": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.memory_capacity.registry"),
    "cpu_admission": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.cpu_admission.registry"),
    "gpu_admission": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.gpu_admission.registry"),
    "context_window": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.context_window.registry"),
    "native_session": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.native_session.registry"),
    "generation_budget": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.generation_budget.registry"),
    "output_receipt": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.output_receipt.registry"),
    "sqlite_replay": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.sqlite_replay.registry"),
    "signed_sources": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.signed_sources.registry"),
    "source_retrieval": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.source_retrieval.registry"),
    "tool_grants": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.tool_grants.registry"),
    "memory_consent": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.memory_consent.registry"),
    "pressure_recovery": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.pressure_recovery.registry"),
    "cancellation": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.cancellation.registry"),
    "cold_restart": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.cold_restart.registry"),
    "first_turn": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.first_turn.registry"),
    "release_gates": lambda: importlib.import_module("skeleton.jeeves.native_fabric.laptop_ops.domains.release_gates.registry"),
}


def registry_module(domain: str):
    if type(domain) is not str or domain not in DOMAINS:
        raise LaptopGateHold("unregistered first-laptop domain")
    return _REGISTRY_LOADERS[domain]()


def list_domains() -> tuple[str, ...]:
    return tuple(sorted(DOMAINS))



def domain_coverage() -> tuple[dict[str, object], ...]:
    """Expose missing source gates without implying successful qualification.

    This is a deterministic inventory over trusted in-repository modules, not
    evidence from a physical laptop. A module's presence proves only that its
    exact source contract can be inspected. The existing evaluate_domain path
    remains authoritative for evaluating untrusted observations.
    """
    output: list[dict[str, object]] = []
    for domain in list_domains():
        implemented = False
        try:
            module = registry_module(domain)
            stages = getattr(module, "STAGES")
            stage_types = getattr(module, "STAGE_TYPES")
            handlers = getattr(module, "HANDLERS")
            describe = getattr(module, "contracts")
            implemented = (
                type(stages) is tuple
                and type(stage_types) is tuple
                and type(handlers) is tuple
                and len(stages) == len(stage_types) == len(handlers) == 8
                and len(set(stages)) == 8
                and all(type(stage) is str for stage in stages)
                and tuple(label for label, _ in stage_types) == stages
                and callable(getattr(module, "evaluate", None))
                and callable(describe)
                and len(describe()) == 8
            )
        except (ImportError, ModuleNotFoundError, AttributeError,
                TypeError, ValueError):
            implemented = False
        output.append({
            "domain": domain,
            "source_contract_present": implemented,
            "native_inference_witnessed": False,
            "physical_device_qualified": False,
            "release_certified": False,
        })
    return tuple(output)


def evaluate_domain(domain: str, evidence: object) -> DomainVerdict:
    name(domain)
    if domain not in DOMAINS:
        raise LaptopGateHold("unregistered first-laptop domain")
    if type(evidence) is not dict:
        raise LaptopGateHold("domain evidence mapping required")
    # Missing incremental modules are explicitly held, not silently skipped.
    try:
        module = registry_module(domain)
    except (ImportError, ModuleNotFoundError) as exc:
        raise LaptopGateHold("required domain module unavailable") from exc
    stages = module.evaluate(evidence)
    return DomainVerdict(domain, tuple(stages),
                         fingerprint({"domain": domain, "evidence": evidence}))
