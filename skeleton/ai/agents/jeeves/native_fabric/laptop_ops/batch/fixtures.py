"""Strictly synthetic 20-domain source cases, never real GGUF witnesses."""
from __future__ import annotations

import importlib
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import (
    LaptopGateHold, canonical,
)
from skeleton.jeeves.native_fabric.laptop_ops.runner import list_domains
from .schema import BUNDLE_INPUT_SCHEMA


def successful_bundle() -> dict[str, dict[str, object]]:
    """Construct one complete synthetic observation from declared predicates."""
    result: dict[str, dict[str, object]] = {}
    for domain in list_domains():
        module = importlib.import_module(
            "skeleton.jeeves.native_fabric.laptop_ops.domains."
            + domain + ".registry"
        )
        result[domain] = successful_evidence(module.STAGE_TYPES)
    return result


def negative_bundle(domain: str, stage: str) -> dict[str, dict[str, object]]:
    """Produce one changed source predicate while every other gate is valid."""
    if domain not in list_domains():
        raise LaptopGateHold("unregistered diagnostic domain")
    source = successful_bundle()
    module = importlib.import_module(
        "skeleton.jeeves.native_fabric.laptop_ops.domains."
        + domain + ".registry"
    )
    changed = dict(mutation_cases(module.STAGE_TYPES))
    if stage not in changed:
        raise LaptopGateHold("undeclared diagnostic stage")
    source[domain] = changed[stage]
    return source


def encode_bundle(source: object) -> bytes:
    """Bounded canonical JSON, clearly marked synthetic source input."""
    return canonical({
        "schema": BUNDLE_INPUT_SCHEMA,
        "domains": source,
    })


__all__ = ["successful_bundle", "negative_bundle", "encode_bundle"]
