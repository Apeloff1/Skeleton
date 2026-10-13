"""Exact-source targeted test inventory for fixed full-app acceptance families.

A test module's presence establishes only *candidate* evidence. Executing
exact-head tests and authenticating the resulting CI run are separate trusted
steps. No source-only scan may mark user journeys or release devices complete.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import re

from .jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError, digest
from .jeeves_completion_census import _json_object

SCHEMA = "skeleton.ai.app_acceptance_test_matrix_projection.v1"
SOURCE = "machine/app_acceptance_test_matrix.json"
SCOPE = "machine/app_completion_scope.json"
MAX_SOURCE_BYTES = 200_000
MAX_MODULES = 80
MAX_BINDINGS = 42
MAX_PAGE = 42
MODULE = re.compile(r"^tests\.test_[a-z][a-z0-9_]{1,120}$")
FAMILY = re.compile(r"^F[0-9]{2}$")


def _test_identity(source, filename):
    """Find ordinary unittest/pytest-style function declarations, never run them."""
    try:
        syntax = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise JeevesAppwideError("malformed targeted test module: " + filename) from exc
    names = []
    for node in syntax.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            names.append(node.name)
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test_"):
                    names.append(node.name + "." + member.name)
    if not names:
        raise JeevesAppwideError("candidate acceptance module has no test cases: " + filename)
    if len(set(names)) != len(names):
        raise JeevesAppwideError("duplicate static acceptance test identity: " + filename)
    return sorted(names)


class JeevesAcceptanceTestMatrix:
    """Selected module-to-product bindings for an independent CI run."""

    def __init__(self, inventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("scanned protected inventory is required")
        inventory._require_scanned()
        self.inv = inventory

    def _build(self, expected_snapshot=None, expected_matrix_sha256=None):
        inv = self.inv
        if expected_snapshot is not None and expected_snapshot != inv._digest:
            raise JeevesAppwideError("stale indexed acceptance source identity")
        text = inv._safe_file(SOURCE, max_size=MAX_SOURCE_BYTES)
        scope_text = inv._safe_file(SCOPE, max_size=MAX_SOURCE_BYTES)
        sha = sha256(text.encode("utf-8")).hexdigest()
        if expected_matrix_sha256 is not None and sha != expected_matrix_sha256:
            raise JeevesAppwideError("matrix source changed since accepted plan")
        matrix = _json_object(text, SOURCE)
        scope = _json_object(scope_text, SCOPE)
        if (matrix.get("schema") != "skeleton.ai.app_acceptance_test_matrix.v1"
            or scope.get("schema") != "skeleton.ai.app_completion_scope.v1"
            or matrix.get("parent_scope") != SCOPE
            or matrix.get("stage") != "implementation_test"
            or matrix.get("runner_mode") != "unittest_module_exact_head"):
            raise JeevesAppwideError("unknown product acceptance test contract")
        policies = matrix.get("policies")
        mandatory = (
            "requires_real_test_execution", "exact_commit_required",
            "source_test_sha_receipts_required",
            "no_success_inference_from_file_presence",
            "matrix_does_not_verify_end_to_end_user_journey",
            "automated_model_or_source_promotion_forbidden",
            "unmapped_families_remain_unknown",
        )
        if type(policies) is not dict or any(policies.get(k) is not True for k in mandatory):
            raise JeevesAppwideError("acceptance test safety policy missing")
        entries = matrix.get("bindings")
        families = scope.get("families")
        if (type(families) is not list or len(families) != 42
            or type(entries) is not list or not 1 <= len(entries) <= MAX_BINDINGS):
            raise JeevesAppwideError("finite acceptance binding scope required")
        scope_ids = [f.get("id") for f in families if type(f) is dict]
        if len(set(scope_ids)) != 42 or any(not isinstance(i, str) for i in scope_ids):
            raise JeevesAppwideError("invalid fixed product family identifiers")
        known = set(scope_ids)
        rows = []
        ids = set()
        modules = {}
        for entry in entries:
            if type(entry) is not dict:
                raise JeevesAppwideError("invalid acceptance binding record")
            family = entry.get("family_id")
            selected = entry.get("unittest_modules")
            if (type(family) is not str or not FAMILY.fullmatch(family)
                or family not in known or family in ids
                or type(selected) is not list or not 1 <= len(selected) <= 4
                or entry.get("scope") != "targeted_regression_subset"
                or entry.get("product_release_qualified") is not False
                or type(entry.get("independent_acceptance_question")) is not str
                or len(entry["independent_acceptance_question"]) < 20):
                raise JeevesAppwideError("unreviewed targeted product acceptance record")
            if len(set(selected)) != len(selected):
                raise JeevesAppwideError("duplicate test module within family")
            ids.add(family)
            for module in selected:
                if type(module) is not str or not MODULE.fullmatch(module):
                    raise JeevesAppwideError("test module name outside curated namespace")
                if module not in modules:
                    path = module.replace(".", "/") + ".py"
                    content = inv._safe_file(path, max_size=MAX_SOURCE_BYTES)
                    cases = _test_identity(content, path)
                    modules[module] = {
                        "module": module,
                        "path": path,
                        "sha256": sha256(content.encode("utf-8")).hexdigest(),
                        "declared_test_case_count": len(cases),
                        "declared_test_cases": cases,
                        "executed": False,
                        "passed_at_exact_head": None,
                    }
            rows.append({
                "family_id": family,
                "independent_acceptance_question": entry["independent_acceptance_question"],
                "workflow_hint": entry.get("workflow_hint"),
                "modules": sorted(selected),
                "test_file_count": len(selected),
                "targeted_cases_declared": sum(modules[m]["declared_test_case_count"]
                                               for m in selected),
                "independent_execution_verified": None,
                "runtime_integration_verified": None,
                "release_device_qualified": False,
            })
        if len(modules) > MAX_MODULES:
            raise JeevesAppwideError("bounded independent acceptance selection exceeded")
        rows.sort(key=lambda item: item["family_id"])
        modules = [modules[key] for key in sorted(modules)]
        report = {
            "schema": SCHEMA,
            "inventory_snapshot": inv._digest,
            "matrix_sha256": sha,
            "scope_sha256": sha256(scope_text.encode()).hexdigest(),
            "family_denominator": 42,
            "curated_test_family_count": len(rows),
            "families_without_curated_tests": sorted(known - ids),
            "unique_test_module_count": len(modules),
            "unique_static_test_case_count": sum(m["declared_test_case_count"]
                                                 for m in modules),
            "selected_modules": [m["module"] for m in modules],
            "module_source_receipts": [
                {"path": m["path"], "sha256": m["sha256"],
                 "declared_test_case_count": m["declared_test_case_count"]}
                for m in modules
            ],
            "tests_executed_by_this_reader": 0,
            "exact_head_passed_from_source_scan": None,
            "no_real_runtime_or_release_claims": True,
            "source_coverage_is_not_accepted_test_evidence": True,
        }
        return {**report, "digest": digest(report)}, rows

    def overview(self, *, expected_snapshot=None, expected_matrix_sha256=None):
        report, _ = self._build(expected_snapshot, expected_matrix_sha256)
        return report

    def page(self, *, offset=0, limit=15, only_unmapped=False,
             expected_matrix_digest=None, expected_snapshot=None,
             expected_matrix_sha256=None):
        if type(offset) is not int or not 0 <= offset <= MAX_BINDINGS:
            raise JeevesAppwideError("bounded acceptance-matrix page offset required")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
            raise JeevesAppwideError("bounded acceptance-matrix page size required")
        if type(only_unmapped) is not bool:
            raise JeevesAppwideError("boolean unmapped acceptance filter required")
        report, rows = self._build(expected_snapshot, expected_matrix_sha256)
        if expected_matrix_digest is not None and expected_matrix_digest != report["digest"]:
            raise JeevesAppwideError("stale product test acceptance projection")
        if only_unmapped:
            rows = [{"family_id": family,
                     "missing_curated_tests": True,
                     "independent_execution_verified": None}
                    for family in report["families_without_curated_tests"]]
        selected = rows[offset:offset + limit]
        body = {
            "schema": SCHEMA + ".page",
            "matrix_digest": report["digest"],
            "offset": offset,
            "limit": limit,
            "total_matches": len(rows),
            "only_unmapped": only_unmapped,
            "next_offset": offset + len(selected)
                if offset + len(selected) < len(rows) else None,
            "families": selected,
            "unverified_tests_not_counted_as_accepted": True,
        }
        return {**body, "digest": digest(body)}
