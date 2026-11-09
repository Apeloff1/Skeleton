"""Gate plane evidence digests for CI / merge notes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List

from skeleton.gate_plane.admit import summarize_outcomes
from skeleton.gate_plane.chaos_scenarios import SCENARIOS, run_all, scenario_catalog
from skeleton.gate_plane.create_app_hooks import build_create_app_gate_plan
from skeleton.gate_plane.proxy_contracts import default_upstreams, validate_proxy_plan
from skeleton.gate_plane.stack import describe_stack, install_order


@dataclass(frozen=True)
class GateEvidence:
    plane: str
    digest: str
    stack_layers: int
    scenarios: int
    upstreams: int
    create_app_wired: bool
    notes: tuple

    def as_dict(self) -> Dict[str, object]:
        return {
            "plane": self.plane,
            "digest": self.digest,
            "stack_layers": self.stack_layers,
            "scenarios": self.scenarios,
            "upstreams": self.upstreams,
            "create_app_wired": self.create_app_wired,
            "notes": list(self.notes),
        }


def digest_plane() -> str:
    payload = {
        "stack": describe_stack(),
        "order": install_order(lifo=True),
        "scenarios": len(SCENARIOS),
        "upstreams": [u.as_dict() for u in default_upstreams()],
        "create_app": build_create_app_gate_plan().as_dict(),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_evidence(*, run_scenarios: bool = False, scenario_limit: int = 50) -> GateEvidence:
    plan = build_create_app_gate_plan()
    proxy = validate_proxy_plan(default_upstreams())
    notes = [
        "Middleware Pack B",
        "install_gate / admit_write / create_app + chaos tests",
        f"proxy_ok={proxy['ok']}",
    ]
    if run_scenarios:
        result = run_all(limit=scenario_limit)
        notes.append(f"scenario_pass={result['passed']}/{result['total']}")
    return GateEvidence(
        plane="gate_plane",
        digest=digest_plane(),
        stack_layers=len(describe_stack()),
        scenarios=len(SCENARIOS),
        upstreams=len(default_upstreams()),
        create_app_wired=plan.wire_install_gate and plan.wire_write_admit,
        notes=tuple(notes),
    )


def pack_b_manifest() -> dict:
    """Static Pack B manifest for merge notes / CoS rollup."""
    from skeleton.gate_plane.chaos_scenarios import SCENARIOS
    from skeleton.gate_plane.operations import digest_registry, registry
    from skeleton.gate_plane.proxy_contracts import default_upstreams
    from skeleton.gate_plane.stack import GATE_LAYERS, install_order
    from skeleton.gate_plane.create_app_hooks import build_create_app_gate_plan

    plan = build_create_app_gate_plan()
    return {
        "pack": "Middleware Pack B",
        "theme": "install_gate / admit_write / create_app + chaos tests",
        "modules": [
            "skeleton/gate_plane/stack.py",
            "skeleton/gate_plane/admit.py",
            "skeleton/gate_plane/chaos_scenarios.py",
            "skeleton/gate_plane/proxy_contracts.py",
            "skeleton/gate_plane/create_app_hooks.py",
            "skeleton/gate_plane/operations.py",
            "skeleton/gate_plane/evidence.py",
            "skeleton/testing/test_gate_plane_pack_b.py",
        ],
        "layer_count": len(GATE_LAYERS),
        "lifo_order": install_order(lifo=True),
        "scenario_count": len(SCENARIOS),
        "upstream_count": len(default_upstreams()),
        "registry_size": len(registry()),
        "registry_digest": digest_registry(),
        "create_app_wire_install_gate": plan.wire_install_gate,
        "create_app_wire_write_admit": plan.wire_write_admit,
        "open_prefixes": list(plan.open_prefixes),
        "sibling": "Apeloff1/gameforge-middleware + gameforge-rs gf-server",
        "notes": [
            "Extend-only; does not rewrite hmac_seal or vault audit",
            "Bare '/' open prefix is exact-only",
            "Chaos scenarios force rung via governor lock for determinism",
            "Proxy contracts are declarative — no live HTTP",
        ],
    }


def render_pack_b_markdown() -> str:
    m = pack_b_manifest()
    lines = [
        f"# {m['pack']}",
        "",
        m["theme"],
        "",
        f"- layers: {m['layer_count']}",
        f"- scenarios: {m['scenario_count']}",
        f"- upstreams: {m['upstream_count']}",
        f"- registry: {m['registry_size']}",
        f"- registry_digest: `{m['registry_digest']}`",
        f"- create_app install_gate: {m['create_app_wire_install_gate']}",
        f"- create_app write_admit: {m['create_app_wire_write_admit']}",
        f"- sibling: {m['sibling']}",
        "",
        "## Modules",
        "",
    ]
    for mod in m["modules"]:
        lines.append(f"- `{mod}`")
    lines += ["", "## Notes", ""]
    for n in m["notes"]:
        lines.append(f"- {n}")
    lines.append("")
    return chr(10).join(lines)
