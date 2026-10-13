"""Canonical required-gate inventory and fail-closed release-readiness boundary.

A workflow file or declaration is not a successful CI run. The gate inventory
cannot sign masterplan volumes, approve merges, mark enterprise superiority or
promote model weights. Exact-head observations belong to the GitHub execution
authority and must be obtained separately from trusted CI.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_completion_census import _json_object

SCHEMA = "skeleton.ai.jeeves_release_gate_inventory.v1"
SOURCE = "machine/p1_required_gate_authority.json"
MAX_PAGE = 40
MAX_GATES = 128


class JeevesReleaseGateInventory:
    """Static release gate witness for source-controlled exact-head policy."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("scanned appwide inventory required")
        inventory._require_scanned()
        self.inventory = inventory

    def _authority(self, expected_snapshot=None):
        inv = self.inventory
        if expected_snapshot is not None and inv._digest != expected_snapshot:
            raise JeevesAppwideError("stale release-gate inventory cursor")
        source_text = inv._safe_file(SOURCE, max_size=256_000)
        doc = _json_object(source_text, SOURCE)
        gates = doc.get("gates", [])
        groups = doc.get("groups", [])
        if (type(gates) is not list or not 1 <= len(gates) <= MAX_GATES
            or type(groups) is not list or not groups):
            raise JeevesAppwideError("invalid bounded canonical gate policy")
        seen = set()
        rows = []
        for gate in gates:
            if type(gate) is not dict:
                raise JeevesAppwideError("non-record required gate entry")
            name = gate.get("id")
            path = gate.get("workflow_file")
            if (type(name) is not str or not 4 <= len(name) <= 128
                or type(path) is not str or not path.startswith(
                    ".github/workflows/") or ".." in path
                or not path.endswith((".yml", ".yaml"))):
                raise JeevesAppwideError("invalid source-controlled gate identifier/path")
            if name in seen:
                raise JeevesAppwideError("duplicate required-gate authority ID")
            seen.add(name)
            statuses = gate.get("accepted_statuses")
            conclusions = gate.get("accepted_conclusions")
            if statuses != ["completed"] or conclusions != ["success"]:
                raise JeevesAppwideError("required gate cannot accept non-success")
            if gate.get("required_for_terminal_p1_promotion") is not True:
                raise JeevesAppwideError("mandatory release gate cannot be optional")
            entry = inv._files.get(path)
            rows.append({
                "id": name,
                "workflow_name": gate.get("workflow_name"),
                "group": gate.get("group"),
                "purpose": str(gate.get("purpose", ""))[:300],
                "workflow_file": path,
                "workflow_source_present": bool(entry and entry.readable),
                "exact_head_required": True,
                "runtime_execution_status": "unobserved",
                "verified_success": False,
                "signed_terminal_acceptance": False,
            })
        group_ids = set()
        for group in groups:
            if type(group) is not dict or type(group.get("name")) is not str:
                raise JeevesAppwideError("invalid gate group")
            name = group["name"]
            if name in group_ids:
                raise JeevesAppwideError("duplicate gate group ID")
            group_ids.add(name)
            refs = group.get("gate_ids")
            if type(refs) is not list or not refs or any(
                type(x) is not str for x in refs
            ):
                raise JeevesAppwideError("invalid gate group membership")
            if len(set(refs)) != len(refs) or not set(refs).issubset(seen):
                raise JeevesAppwideError("unknown or repeated group gate ID")
        undeclared_groups = sorted(set(row["group"] for row in rows) - group_ids)
        if undeclared_groups:
            raise JeevesAppwideError("required gate references undeclared group")
        grouped = [member for group in groups for member in group["gate_ids"]]
        if len(grouped) != len(seen) or set(grouped) != seen:
            raise JeevesAppwideError("required gate missing or multiply assigned")
        terminal = doc.get("terminal_policy")
        if type(terminal) is not dict:
            raise JeevesAppwideError("terminal P1 policy missing")
        mandatory = (
            terminal.get("required_gate_count") == len(gates)
            and terminal.get("all_required_gates_must_pass") is True
            and terminal.get("observation_set_must_bind_one_exact_head") is True
            and terminal.get("self_promotion_forbidden") is True
            and terminal.get("authority_digest_must_match") is True
            and doc.get("exact_head_required") is True
        )
        if not mandatory:
            raise JeevesAppwideError("required gate terminal promotion policy weakened")
        rows.sort(key=lambda x: x["id"])
        return rows, {
            "schema": SCHEMA,
            "inventory_snapshot": inv._digest,
            "authority_sha256": sha256(source_text.encode()).hexdigest(),
            "required_gates": len(rows),
            "declared_gate_groups": len(group_ids),
            "sources_present": sum(int(r["workflow_source_present"]) for r in rows),
            "sources_missing": sum(int(not r["workflow_source_present"]) for r in rows),
            "unobserved_exact_head_checks": len(rows),
            "independently_verified_checks": 0,
            "failed_or_queued_never_count_as_pass": True,
            "all_required_checks_pass": False,
            "release_qualified": False,
            "self_signoff_performed": False,
            "no_ci_queries_or_releases_performed": True,
        }

    def overview(self, *, expected_snapshot=None):
        _, body = self._authority(expected_snapshot)
        return {**body, "digest": digest(body)}

    def page(self, *, offset=0, limit=26, only_missing=False,
             expected_inventory_digest=None, expected_snapshot=None):
        if type(offset) is not int or not 0 <= offset <= MAX_GATES:
            raise JeevesAppwideError("bounded non-negative gate page required")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded positive gate page limit required")
        if type(only_missing) is not bool:
            raise JeevesAppwideError("boolean missing-gate filter required")
        rows, body = self._authority(expected_snapshot)
        report = {**body, "digest": digest(body)}
        if (expected_inventory_digest is not None
            and expected_inventory_digest != report["digest"]):
            raise JeevesAppwideError("stale release authority receipt")
        if only_missing:
            rows = [g for g in rows if not g["workflow_source_present"]]
        selected = rows[offset:offset+limit]
        result = {
            "schema": SCHEMA + ".page",
            "authority_digest": report["digest"],
            "offset": offset, "limit": limit,
            "total_matches": len(rows), "only_missing": only_missing,
            "next_offset": offset+len(selected) if offset+len(selected) < len(rows)
                else None,
            "gates": selected,
            "no_untrusted_ci_result_promotions": True,
        }
        return {**result, "digest": digest(result)}
