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
