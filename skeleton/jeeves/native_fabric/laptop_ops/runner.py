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
            module = importlib.import_module(
                "skeleton.jeeves.native_fabric.laptop_ops.domains."
                + domain + ".registry"
            )
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
        module = importlib.import_module(
            "skeleton.jeeves.native_fabric.laptop_ops.domains."
            + domain + ".registry"
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise LaptopGateHold("required domain module unavailable") from exc
    stages = module.evaluate(evidence)
    return DomainVerdict(domain, tuple(stages),
                         fingerprint({"domain": domain, "evidence": evidence}))
