"""Explicitly inspect all 20 approved source-stage registry contracts.

Importable modules and self-described observations are never model or
device proof. The inventory must be structurally complete before admission.
"""
from __future__ import annotations

from skeleton.jeeves.native_fabric.laptop_ops.contracts import (
    LaptopGateHold, fingerprint,
)
from skeleton.jeeves.native_fabric.laptop_ops.predicates import required_keys
from skeleton.jeeves.native_fabric.laptop_ops.runner import (
    domain_coverage, list_domains, registry_module,
)
from .limits import DOMAIN_COUNT, STAGES_PER_DOMAIN


def manifest() -> dict[str, object]:
    """Frozen sorted source-domain shape with non-authority contracts."""
    domains = list_domains()
    if len(domains) != DOMAIN_COUNT:
        raise LaptopGateHold("first-laptop domain roster is not exactly twenty")
    coverage = domain_coverage()
    if len(coverage) != DOMAIN_COUNT or any(
        not row["source_contract_present"] for row in coverage
    ):
        raise LaptopGateHold("missing mandatory source safeguards")
    declaration: list[dict[str, object]] = []
    for domain in domains:
        try:
            module = registry_module(domain)
            names = module.STAGES
            kinds = module.STAGE_TYPES
            docs = module.contracts()
        except (AttributeError, ImportError, TypeError, ValueError) as exc:
            raise LaptopGateHold("unavailable source contract") from exc
        if (type(names) is not tuple
                or type(kinds) is not tuple
                or len(names) != STAGES_PER_DOMAIN
                or len(kinds) != STAGES_PER_DOMAIN
                or type(docs) is not tuple
                or len(docs) != STAGES_PER_DOMAIN):
            raise LaptopGateHold("invalid source domain metadata")
        stages: list[dict[str, object]] = []
        for name, (stage, kind), doc in zip(names, kinds, docs):
            if (stage != name or type(doc) is not dict
                    or doc.get("domain") != domain
                    or doc.get("stage") != name
                    or doc.get("predicate") != kind
                    or doc.get("required_fields") != list(required_keys(kind, name))
                    or doc.get("operator_proof_is_insufficient_for_activation") is not True
                    or doc.get("device_qualified") is not False):
                raise LaptopGateHold("mismatched source stage input contract")
            stages.append({
                "name": name,
                "predicate": kind,
                "required_fields": list(required_keys(kind, name)),
            })
        declaration.append({"domain": domain, "stages": stages})
    raw = {"schema": "jeeves.laptop_ops.bundle_catalog.v1",
           "domains": declaration,
           "native_inference_witnessed": False,
           "physical_device_qualified": False,
           "release_certified": False}
    return {**raw, "manifest_sha256": fingerprint(raw)}


__all__ = ["manifest"]
