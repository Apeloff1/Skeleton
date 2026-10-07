"""Static workflow-contract regressions for the auto-merge control plane."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.check_automerge_contract import (
    FORBIDDEN_IMPORTS,
    MODULES,
    PACKAGE,
    REQUIRED_RECONCILE_PERMISSIONS,
    ROOT,
    WORKFLOW,
    _cross_file_findings,
    _defined_symbols,
    _imports,
    _line_block,
    _source_findings,
    _workflow_findings,
    check,
)


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_repository_contract_is_clean():
    assert check() == ()


def test_workflow_exists():
    assert WORKFLOW.exists()
    assert WORKFLOW.is_file()


def test_all_runtime_modules_exist():
    for name in MODULES:
        assert (PACKAGE / name).is_file(), name


def test_workflow_uses_trusted_default_branch_checkout():
    text = _workflow_text()
    assert text.count("github.event.repository.default_branch") >= 3
    assert text.count("persist-credentials: false") >= 2


def test_workflow_does_not_use_pull_request_target():
    assert "pull_request_target:" not in _workflow_text()


def test_workflow_has_empty_global_permissions():
    assert "permissions: {}" in _workflow_text()


def test_validate_job_is_read_only():
    block = _line_block(_workflow_text(), "validate:")
    assert "contents: read" in block
    assert "actions: write" not in block
    assert "pull-requests: write" not in block


@pytest.mark.parametrize(
    "permission,value",
    sorted(REQUIRED_RECONCILE_PERMISSIONS.items()),
)
def test_reconcile_job_has_expected_narrow_permissions(permission, value):
    reconcile = _line_block(_workflow_text(), "reconcile:")
    permissions = _line_block(reconcile, "permissions:")
    assert f"{permission}: {value}" in permissions


def test_reconcile_job_invokes_canonical_cli():
    reconcile = _line_block(_workflow_text(), "reconcile:")
    assert "python -m skeleton.pr_automation.automerge_cli" in reconcile


def test_reconcile_job_installs_runtime_dependencies_before_cli():
    reconcile = _line_block(_workflow_text(), "reconcile:")
    pydantic = reconcile.find('"pydantic>=2,<3"')
    settings = reconcile.find('"pydantic-settings>=2.1,<3"')
    cli = reconcile.find("python -m skeleton.pr_automation.automerge_cli")
    assert pydantic >= 0
    assert settings >= 0
    assert cli > pydantic
    assert cli > settings


def test_stack_mutation_forces_fresh_reconciliation():
    reconcile = _line_block(_workflow_text(), "reconcile:")
    assert 'AUTOMERGE_STOP_AFTER_STACK_MUTATION: "true"' in reconcile


def test_post_merge_dispatch_is_enabled():
    reconcile = _line_block(_workflow_text(), "reconcile:")
    assert 'AUTOMERGE_DISPATCH_POST_MERGE: "true"' in reconcile


def test_workflow_retains_tamper_evidence_artifact():
    reconcile = _line_block(_workflow_text(), "reconcile:")
    assert "actions/upload-artifact@" in reconcile
    assert "if-no-files-found: error" in reconcile
    assert ".automerge/ledger.jsonl" in reconcile
    assert ".automerge/report.json" in reconcile


def test_control_plane_concurrency_is_non_preemptive():
    concurrency = _line_block(_workflow_text(), "concurrency:")
    assert "github.repository" in concurrency
    assert "cancel-in-progress: false" in concurrency


def test_workflow_has_no_manual_recovery_trigger():
    assert "workflow_dispatch:" not in _workflow_text()


def test_active_policy_disables_review_gates():
    reconcile = _line_block(_workflow_text(), "reconcile:")
    assert 'AUTOMERGE_REQUIRED_APPROVALS: "0"' in reconcile
    assert 'AUTOMERGE_REQUIRE_RESOLVED_THREADS: "false"' in reconcile
    assert 'AUTOMERGE_REQUIRE_NO_CHANGES_REQUESTED: "false"' in reconcile


def test_workflow_has_periodic_reconciliation_trigger():
    assert "schedule:" in _workflow_text()


def test_workflow_wakes_on_merge_readiness_completion():
    text = _workflow_text()
    assert "workflow_run:" in text
    assert '"Merge Readiness"' in text


def test_workflow_compiles_every_runtime_module():
    validate = _line_block(_workflow_text(), "validate:")
    for name in MODULES:
        assert f"skeleton/pr_automation/{name}" in validate


def test_workflow_runs_every_focused_regression_family():
    validate = _line_block(_workflow_text(), "validate:")
    required = (
        "test_automerge_model.py",
        "test_automerge_evidence.py",
        "test_automerge_policy.py",
        "test_automerge_stack.py",
        "test_automerge_engine.py",
        "test_automerge_contract.py",
    )
    for name in required:
        assert name in validate


def test_workflow_installs_pytest_before_test_run():
    validate = _line_block(_workflow_text(), "validate:")
    install = validate.find("pytest>=8,<9")
    run = validate.find("python -m pytest")
    assert install >= 0
    assert run > install


@pytest.mark.parametrize(
    "marker",
    [
        "persist-credentials: true",
        "permissions: write-all",
        "permissions: read-all",
        "curl | sh",
        "wget | sh",
        "sudo ",
    ],
)
def test_forbidden_workflow_markers_absent(marker):
    assert marker not in _workflow_text()


def test_source_modules_parse():
    for name in MODULES:
        path = PACKAGE / name
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_source_modules_do_not_import_forbidden_execution_packages():
    for name in MODULES:
        path = PACKAGE / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = _imports(tree)
        assert not imported.intersection(FORBIDDEN_IMPORTS), (
            name,
            sorted(imported.intersection(FORBIDDEN_IMPORTS)),
        )


def test_source_modules_do_not_use_eval_or_exec():
    for name in MODULES:
        source = (PACKAGE / name).read_text(encoding="utf-8")
        assert "eval(" not in source, name
        assert "exec(" not in source, name


def test_source_modules_do_not_use_dynamic_import():
    for name in MODULES:
        source = (PACKAGE / name).read_text(encoding="utf-8")
        assert "__import__(" not in source, name


def test_engine_has_mutation_boundary_revalidation():
    source = (PACKAGE / "automerge_engine.py").read_text(encoding="utf-8")
    assert "_revalidate_selection(" in source
    assert "expected_default_head" in source
    assert "immutable_identity_equal" in source


def test_engine_discards_snapshot_after_stack_mutation():
    source = (PACKAGE / "automerge_engine.py").read_text(encoding="utf-8")
    assert "stop_after_stack_mutation" in source
    assert "break" in source


def test_direct_merge_binds_expected_head_sha():
    source = (PACKAGE / "automerge_github.py").read_text(encoding="utf-8")
    assert '"sha": expected_head_sha' in source


def test_github_adapter_uses_bounded_pagination():
    source = (PACKAGE / "automerge_github.py").read_text(encoding="utf-8")
    assert "max_pages" in source
    assert "bounded pagination exceeded" in source


def test_github_adapter_uses_bounded_retries():
    source = (PACKAGE / "automerge_github.py").read_text(encoding="utf-8")
    assert "self.retries" in source
    assert "attempt >= self.retries" in source


def test_policy_keeps_own_trust_surface_critical_and_evidence_gated():
    source = (PACKAGE / "automerge_policy.py").read_text(encoding="utf-8")
    assert '"skeleton/pr_automation/"' in source
    assert '".github/workflows/"' in source
    assert '".github/actions/"' in source
    assert "RiskTier.CRITICAL" in source
    assert "SECURITY_WORKFLOWS" in source
    assert "evidence_complete(" in source
    assert "stability_elapsed(" in source


def test_policy_requires_stability_window():
    source = (PACKAGE / "automerge_policy.py").read_text(encoding="utf-8")
    assert "stability_elapsed(" in source
    assert "exact_head_success_stability_window_not_elapsed" in source


def test_evidence_is_exact_head_scoped():
    source = (PACKAGE / "automerge_evidence.py").read_text(encoding="utf-8")
    assert "run.head_sha != head_sha" in source
    assert 'event="pull_request"' in source


def test_stack_graph_detects_cycles_and_orphans():
    source = (PACKAGE / "automerge_stack.py").read_text(encoding="utf-8")
    assert "_find_cycles" in source
    assert "StackRelation.ORPHAN" in source
    assert "child_base_sha_mismatch" in source


def test_ledger_is_hash_chained():
    source = (PACKAGE / "automerge_ledger.py").read_text(encoding="utf-8")
    assert "previous_hash" in source
    assert "record_hash" in source
    assert "sha256" in source
    assert "ledger previous hash mismatch" in source


def test_cli_defaults_to_fail_closed_required_workflows():
    source = (PACKAGE / "automerge_cli.py").read_text(encoding="utf-8")
    for name in (
        "CI/CD",
        "Merge Readiness",
        "Secret scanning",
        "Malware Gate",
        "Repository Hygiene Gate",
        "Artifact Policy",
        "Provenance Policy",
        "PR Hygiene",
    ):
        assert name in source


def test_cross_file_contract_checker_is_clean():
    assert _cross_file_findings() == []


def test_source_contract_checker_is_clean():
    assert _source_findings() == []


def test_workflow_contract_checker_is_clean():
    assert _workflow_findings(_workflow_text()) == []


def test_line_block_extracts_nested_section():
    text = "root:\n  a: 1\n  child:\n    b: 2\nnext: 3\n"
    assert _line_block(text, "root:") == "root:\n  a: 1\n  child:\n    b: 2"


def test_line_block_missing_header_empty():
    assert _line_block("a: 1\n", "missing:") == ""


def test_defined_symbols_includes_classes_and_functions():
    tree = ast.parse(
        "class A:\n    pass\n\ndef b():\n    pass\n\nasync def c():\n    pass\n"
    )
    assert _defined_symbols(tree) == {"A", "b", "c"}


def test_import_scanner_finds_root_modules():
    tree = ast.parse(
        "import os.path\nfrom urllib.parse import quote\n"
    )
    assert _imports(tree) == {"os", "urllib"}


def test_checker_root_is_repository_root():
    assert (ROOT / ".github").exists()
    assert (ROOT / "skeleton").exists()


def test_workflow_path_is_under_repository_root():
    assert WORKFLOW.relative_to(ROOT) == Path(
        ".github/workflows/automerge-control-plane.yml"
    )
