"""Allowlisted domain dispatcher with deterministic all-stages-required results."""
from __future__ import annotations
from .contracts import LaptopGateHold, DomainVerdict, fingerprint, name

DOMAINS = frozenset((
    "bootstrap", "model_manifest", "tokenizer_identity", "memory_capacity",
    "cpu_admission", "gpu_admission", "context_window", "native_session",
    "generation_budget", "output_receipt", "sqlite_replay", "signed_sources",
    "source_retrieval", "tool_grants", "memory_consent", "pressure_recovery",
    "cancellation", "cold_restart", "first_turn", "release_gates",
))


def list_domains() -> tuple[str, ...]:
    return tuple(sorted(DOMAINS))



def registry(domain: str):
    """Load only explicitly approved source-domain registries (no computed import names)."""
    if domain not in DOMAINS:
        raise LaptopGateHold("unregistered first-laptop domain")
    if domain == "bootstrap":
        from .domains.bootstrap import registry as module
    elif domain == "model_manifest":
        from .domains.model_manifest import registry as module
    elif domain == "tokenizer_identity":
        from .domains.tokenizer_identity import registry as module
    elif domain == "memory_capacity":
        from .domains.memory_capacity import registry as module
    elif domain == "cpu_admission":
        from .domains.cpu_admission import registry as module
    elif domain == "gpu_admission":
        from .domains.gpu_admission import registry as module
    elif domain == "context_window":
        from .domains.context_window import registry as module
    elif domain == "native_session":
        from .domains.native_session import registry as module
    elif domain == "generation_budget":
        from .domains.generation_budget import registry as module
    elif domain == "output_receipt":
        from .domains.output_receipt import registry as module
    elif domain == "sqlite_replay":
        from .domains.sqlite_replay import registry as module
    elif domain == "signed_sources":
        from .domains.signed_sources import registry as module
    elif domain == "source_retrieval":
        from .domains.source_retrieval import registry as module
    elif domain == "tool_grants":
        from .domains.tool_grants import registry as module
    elif domain == "memory_consent":
        from .domains.memory_consent import registry as module
    elif domain == "pressure_recovery":
        from .domains.pressure_recovery import registry as module
    elif domain == "cancellation":
        from .domains.cancellation import registry as module
    elif domain == "cold_restart":
        from .domains.cold_restart import registry as module
    elif domain == "first_turn":
        from .domains.first_turn import registry as module
    elif domain == "release_gates":
        from .domains.release_gates import registry as module
    return module


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
            module = registry(domain)
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
        module = registry(domain)
    except (ImportError, ModuleNotFoundError) as exc:
        raise LaptopGateHold("required domain module unavailable") from exc
    stages = module.evaluate(evidence)
    return DomainVerdict(domain, tuple(stages),
                         fingerprint({"domain": domain, "evidence": evidence}))
