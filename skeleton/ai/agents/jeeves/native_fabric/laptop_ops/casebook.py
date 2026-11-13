"""Synthetic contract fixtures; never represent source-only cases as real runs."""
from __future__ import annotations
from .contracts import LaptopGateHold, canonical
from .predicates import sample


def successful_evidence(stage_types: tuple[tuple[str, str], ...]):
    if type(stage_types) is not tuple or len(stage_types) != 8:
        raise LaptopGateHold("complete eight-stage fixture set required")
    if len({name for name, _ in stage_types}) != 8:
        raise LaptopGateHold("duplicate synthetic safeguard name")
    return {label: sample(kind) for label, kind in stage_types}


def mutation_cases(stage_types: tuple[tuple[str, str], ...]):
    """Bounded negative cases used only by source parser tests."""
    baseline = successful_evidence(stage_types)
    mutations = []
    for stage, kind in stage_types:
        bad = {key: dict(value) for key, value in baseline.items()}
        if kind == "true":
            bad[stage]["verified"] = False
        elif kind == "false":
            bad[stage]["blocked"] = True
        elif kind == "sha_equal":
            bad[stage]["observed_sha256"] = "b" * 64
        elif kind == "capacity":
            bad[stage]["available"] = 0
        elif kind == "bounded":
            bad[stage]["used"] = bad[stage]["limit"] + 1
        elif kind == "fresh":
            bad[stage]["expires_at"] = bad[stage]["observed_at"]
        elif kind == "same_owner":
            bad[stage]["active_owner"] = "other"
        elif kind == "monotonic":
            bad[stage]["previous"] = bad[stage]["current"] + 1
        else:
            raise LaptopGateHold("unknown synthetic mutation")
        canonical(bad)
        mutations.append((stage, bad))
    return tuple(mutations)
