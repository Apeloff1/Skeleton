"""Static dispatch coverage for registered appwide Jeeves adapter contract.

This inspects the actual checked-out owner module through the protected
inventory. It never imports an arbitrary indexed file, executes a tool, or
confuses syntactic dispatch coverage with real functional/permission evidence.
"""
from __future__ import annotations

import ast
from hashlib import sha256

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, OPERATIONS, digest,
)

SCHEMA = "skeleton.ai.jeeves_adapter_dispatch_audit.v1"
OWNER = "skeleton/ai/game_builder/jeeves_appwide_fabric.py"
MAX_PAGE = 80


def _action_literals(owner_text: str) -> set[str]:
    try:
        tree = ast.parse(owner_text, filename=OWNER)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise JeevesAppwideError("malformed canonical Jeeves dispatcher") from exc
    matches = [
        item for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == "JeevesAppwideRuntime"
    ]
    if len(matches) != 1:
        raise JeevesAppwideError("canonical Jeeves runtime class missing/ambiguous")
    methods = [item for item in matches[0].body
               if isinstance(item, ast.FunctionDef) and item.name == "invoke"]
    if len(methods) != 1:
        raise JeevesAppwideError("canonical invoke entrypoint missing/ambiguous")
    accepted = set()
    for node in ast.walk(methods[0]):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name):
            continue
        if node.left.id != "action" or len(node.ops) != 1 or len(node.comparators) != 1:
            continue
        op, value = node.ops[0], node.comparators[0]
        if isinstance(op, ast.Eq) and isinstance(value, ast.Constant):
            if type(value.value) is str:
                accepted.add(value.value)
        if isinstance(op, ast.In) and isinstance(value, (ast.Tuple, ast.List)):
            for part in value.elts:
                if isinstance(part, ast.Constant) and type(part.value) is str:
                    accepted.add(part.value)
    return accepted


class JeevesAdapterDispatchAudit:
    """Audit action registration and syntactic dispatch coverage only."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical scan required")
        inventory._require_scanned()
        self.inventory = inventory

    def _inspect(self, *, expected_snapshot=None):
        if (expected_snapshot is not None and
            expected_snapshot != self.inventory._digest):
            raise JeevesAppwideError("stale dispatcher source inventory")
        source = self.inventory._safe_file(OWNER, max_size=256_000)
        dispatch = _action_literals(source)
        contract = {}
        for action, entry in sorted(OPERATIONS.items()):
            if (type(action) is not str or not action or type(entry) is not tuple
                or len(entry) != 3 or entry[0] not in
                ("read", "compute", "proposal", "external_effect") or type(entry[1]) is not str
                or type(entry[2]) is not bool):
                raise JeevesAppwideError("invalid reviewed Jeeves operation descriptor")
            contract[action] = {
                "action": action,
                "effect": entry[0],
                "operator_gate": entry[2],
                "static_dispatch_declared": action in dispatch,
                "runtime_executed_and_verified": False,
                "automatic_execution_authorized": False,
                "source_owner": OWNER,
            }
        missing = sorted(set(contract) - dispatch)
        unknown = sorted(dispatch - set(contract))
        return contract, {
            "schema": SCHEMA,
            "source_sha256": sha256(source.encode("utf-8")).hexdigest(),
            "inventory_snapshot": self.inventory._digest,
            "registered_actions": len(contract),
            "syntactically_dispatched_actions": sum(int(row[
                "static_dispatch_declared"]) for row in contract.values()),
            "declared_but_not_dispatched": missing,
            "dispatch_without_registry_entry": unknown,
            "registered_read_only": sum(int(x["effect"] == "read")
                                        for x in contract.values()),
            "registered_compute": sum(int(x["effect"] == "compute")
                                      for x in contract.values()),
            "registered_proposal": sum(int(x["effect"] == "proposal")
                                       for x in contract.values()),
            "registered_external_effect": sum(int(x["effect"] == "external_effect")
                                               for x in contract.values()),
            "review_gated_actions": sum(int(x["operator_gate"])
                                        for x in contract.values()),
            "functional_appwide_coverage_percent": None,
            "runtime_effects_executed": 0,
            "all_discovered_sources_automatically_callable": False,
            "source_authority_changed": False,
        }

    def overview(self, *, expected_snapshot=None):
        _, body = self._inspect(expected_snapshot=expected_snapshot)
        return {**body, "digest": digest(body)}

    def page(self, *, offset=0, limit=25, expected_audit_digest=None,
             expected_snapshot=None, only_missing=False):
        if type(offset) is not int or not 0 <= offset <= 1000:
            raise JeevesAppwideError("bounded adapter audit offset required")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded adapter audit page size required")
        if type(only_missing) is not bool:
            raise JeevesAppwideError("boolean adapter gap filter required")
        actions, body = self._inspect(expected_snapshot=expected_snapshot)
        audit_digest = digest(body)
        if (expected_audit_digest is not None and
            expected_audit_digest != audit_digest):
            raise JeevesAppwideError("stale adapter dispatch evidence")
        rows = [actions[a] for a in sorted(actions)]
        if only_missing:
            rows = [row for row in rows if not row["static_dispatch_declared"]]
        selected = rows[offset:offset + limit]
        result = {
            "schema": SCHEMA + ".page",
            "audit_digest": audit_digest,
            "offset": offset, "limit": limit,
            "only_missing": only_missing,
            "total_matches": len(rows),
            "next_offset": offset + len(selected)
                if offset + len(selected) < len(rows) else None,
            "adapters": selected,
            "syntax_is_not_functional_execution_proof": True,
        }
        return {**result, "digest": digest(result)}
