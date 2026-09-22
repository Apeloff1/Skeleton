"""Fail-closed static contract checker for auto-merge workflow and runtime.

This checker intentionally avoids a YAML dependency so it can run in the
repository's earliest quality gates.  It validates high-value structural
invariants against the workflow text and Python source inventory.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "automerge-control-plane.yml"
PACKAGE = ROOT / "skeleton" / "pr_automation"
MODULES = (
    "automerge_model.py",
    "automerge_evidence.py",
    "automerge_policy.py",
    "automerge_stack.py",
    "automerge_github.py",
    "automerge_ledger.py",
    "automerge_engine.py",
    "automerge_cli.py",
)

FORBIDDEN_WORKFLOW_MARKERS = (
    "pull_request_target:",
    "persist-credentials: true",
    "permissions: write-all",
    "permissions: read-all",
    "curl | sh",
    "wget | sh",
    "sudo ",
)

FORBIDDEN_IMPORTS = {
    "subprocess",
    "socket",
    "pty",
    "shlex",
    "paramiko",
    "requests",
}

REQUIRED_RECONCILE_PERMISSIONS = {
    "actions": "write",
    "checks": "read",
    "contents": "write",
    "pull-requests": "write",
    "statuses": "read",
}

REQUIRED_WORKFLOW_TRIGGERS = (
    "workflow_run:",
    "schedule:",
)

FORBIDDEN_MANUAL_TRIGGERS = (
    "workflow_dispatch:",
)

REQUIRED_SOURCE_SYMBOLS = {
    "automerge_model.py": {
        "AutoMergePolicy",
        "CandidateSnapshot",
        "MergeDecision",
        "MutationReceipt",
        "ReconcileReport",
    },
    "automerge_evidence.py": {
        "aggregate_required_workflows",
        "summarize_evidence",
        "stability_elapsed",
    },
    "automerge_policy.py": {
        "classify_paths",
        "evaluate_candidate",
        "requirements_for_candidate",
    },
    "automerge_stack.py": {
        "build_stack_graph",
        "landing_plan",
        "validate_graph",
    },
    "automerge_github.py": {
        "GitHubAutoMergeClient",
    },
    "automerge_ledger.py": {
        "MergeLedger",
    },
    "automerge_engine.py": {
        "reconcile",
        "build_iteration",
        "select_mutation",
    },
    "automerge_cli.py": {
        "policy_from_env",
        "engine_config_from_env",
        "run",
    },
}


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    message: str
    path: str

    def render(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to read {path}: {exc}") from exc


def _line_block(text: str, header: str) -> str:
    lines = text.splitlines()
    start = None
    base_indent = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            base_indent = len(line) - len(line.lstrip())
            break
    if start is None or base_indent is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1 :]:
        if not line.strip():
            out.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent:
            break
        out.append(line)
    return "\n".join(out)


def _workflow_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    rel = str(WORKFLOW.relative_to(ROOT))

    if not text.startswith("name: Auto-Merge Control Plane\n"):
        findings.append(
            Finding(
                "workflow-name",
                "workflow must have the canonical Auto-Merge Control Plane name",
                rel,
            )
        )

    for marker in REQUIRED_WORKFLOW_TRIGGERS:
        if marker not in text:
            findings.append(
                Finding(
                    "missing-trigger",
                    f"required trigger {marker!r} is absent",
                    rel,
                )
            )

    for marker in FORBIDDEN_MANUAL_TRIGGERS:
        if marker in text:
            findings.append(
                Finding(
                    "manual-trigger",
                    f"manual auto-merge trigger {marker!r} must remain disabled",
                    rel,
                )
            )

    for marker in FORBIDDEN_WORKFLOW_MARKERS:
        if marker in text:
            findings.append(
                Finding(
                    "forbidden-workflow-marker",
                    f"forbidden marker {marker!r} is present",
                    rel,
                )
            )

    if re.search(r"(?m)^permissions:\s*\{\}\s*$", text) is None:
        findings.append(
            Finding(
                "top-permissions",
                "workflow-wide permissions must be empty",
                rel,
            )
        )

    concurrency = _line_block(text, "concurrency:")
    if "cancel-in-progress: false" not in concurrency:
        findings.append(
            Finding(
                "concurrency",
                "control plane must not cancel an active reconciliation",
                rel,
            )
        )
    if "github.repository" not in concurrency:
        findings.append(
            Finding(
                "concurrency",
                "concurrency group must be repository scoped",
                rel,
            )
        )

    reconcile = _line_block(text, "reconcile:")
    if not reconcile:
        findings.append(
            Finding("missing-job", "reconcile job is absent", rel)
        )
        return findings

    permissions = _line_block(reconcile, "permissions:")
    for key, value in REQUIRED_RECONCILE_PERMISSIONS.items():
        expected = f"{key}: {value}"
        if expected not in permissions:
            findings.append(
                Finding(
                    "job-permission",
                    f"reconcile job must declare {expected}",
                    rel,
                )
            )

    validate = _line_block(text, "validate:")
    if "contents: read" not in validate:
        findings.append(
            Finding(
                "validation-permission",
                "validation job must be contents-read only",
                rel,
            )
        )
    if "actions: write" in validate or "pull-requests: write" in validate:
        findings.append(
            Finding(
                "validation-permission",
                "validation job must not receive mutation scopes",
                rel,
            )
        )

    if text.count("persist-credentials: false") < 2:
        findings.append(
            Finding(
                "checkout-credentials",
                "both jobs must disable checkout credential persistence",
                rel,
            )
        )

    if text.count("github.event.repository.default_branch") < 3:
        findings.append(
            Finding(
                "trusted-checkout",
                "workflow must bind trusted checkout and runtime base to default branch",
                rel,
            )
        )

    if "python -m skeleton.pr_automation.automerge_cli" not in reconcile:
        findings.append(
            Finding(
                "runtime-entrypoint",
                "reconcile job must invoke the canonical Python entrypoint",
                rel,
            )
        )

    if "AUTOMERGE_DISPATCH_POST_MERGE: \"true\"" not in reconcile:
        findings.append(
            Finding(
                "post-merge-evidence",
                "post-merge workflow dispatch must be enabled",
                rel,
            )
        )

    if "AUTOMERGE_STOP_AFTER_STACK_MUTATION: \"true\"" not in reconcile:
        findings.append(
            Finding(
                "stack-revalidation",
                "stack mutation must force a later fresh reconciliation",
                rel,
            )
        )

    if "actions/upload-artifact@" not in reconcile:
        findings.append(
            Finding(
                "evidence-retention",
                "reconciliation evidence artifact upload is required",
                rel,
            )
        )

    if "if-no-files-found: error" not in reconcile:
        findings.append(
            Finding(
                "evidence-retention",
                "missing evidence files must fail the artifact step",
                rel,
            )
        )

    return findings


def _defined_symbols(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
    return out


def _imports(tree: ast.Module) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result


def _source_findings() -> list[Finding]:
    findings: list[Finding] = []
    for name in MODULES:
        path = PACKAGE / name
        rel = str(path.relative_to(ROOT))
        if not path.exists():
            findings.append(
                Finding("missing-module", "required module is absent", rel)
            )
            continue

        source = _read(path)
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    "syntax",
                    f"module does not parse: {exc.msg} at line {exc.lineno}",
                    rel,
                )
            )
            continue

        imported = _imports(tree)
        forbidden = sorted(imported.intersection(FORBIDDEN_IMPORTS))
        if forbidden:
            findings.append(
                Finding(
                    "forbidden-import",
                    "privileged auto-merge modules may not import "
                    + ", ".join(forbidden),
                    rel,
                )
            )

        required = REQUIRED_SOURCE_SYMBOLS.get(name, set())
        missing = sorted(required.difference(_defined_symbols(tree)))
        if missing:
            findings.append(
                Finding(
                    "missing-symbol",
                    "required public symbols absent: " + ", ".join(missing),
                    rel,
                )
            )

        if "eval(" in source or "exec(" in source:
            findings.append(
                Finding(
                    "dynamic-execution",
                    "dynamic eval/exec is forbidden in auto-merge runtime",
                    rel,
                )
            )

        if "__import__(" in source:
            findings.append(
                Finding(
                    "dynamic-import",
                    "runtime-selected imports are forbidden",
                    rel,
                )
            )

    return findings


def _cross_file_findings() -> list[Finding]:
    findings: list[Finding] = []
    engine = _read(PACKAGE / "automerge_engine.py")
    github = _read(PACKAGE / "automerge_github.py")
    policy = _read(PACKAGE / "automerge_policy.py")
    model = _read(PACKAGE / "automerge_model.py")

    checks = (
        (
            "one-mutation-snapshot",
            "_revalidate_selection(" in engine
            and "client.branch_head(policy.default_branch) != expected_default_head" in engine,
            "engine must re-read candidate and bind default-branch head before mutation",
            "skeleton/pr_automation/automerge_engine.py",
        ),
        (
            "expected-head",
            '"sha": expected_head_sha' in github,
            "direct merge must bind expected head SHA server-side",
            "skeleton/pr_automation/automerge_github.py",
        ),
        (
            "stack-stop",
            "stop_after_stack_mutation" in engine,
            "stack landing must support forced exact-head revalidation",
            "skeleton/pr_automation/automerge_engine.py",
        ),
        (
            "fork-policy",
            "same_repository_only" in model and "fork_head_not_allowed" in policy,
            "fork candidates must fail closed by default",
            "skeleton/pr_automation/automerge_policy.py",
        ),
        (
            "stability-window",
            "stability_elapsed(" in policy,
            "successful checks must observe a stability window before mutation",
            "skeleton/pr_automation/automerge_policy.py",
        ),
        (
            "tamper-evidence",
            "ledger.append_decision" in engine and "ledger.append_receipt" in engine,
            "engine must record decision and mutation evidence",
            "skeleton/pr_automation/automerge_engine.py",
        ),
    )

    for code, ok, message, path in checks:
        if not ok:
            findings.append(Finding(code, message, path))
    return findings


def check() -> tuple[Finding, ...]:
    if not WORKFLOW.exists():
        return (
            Finding(
                "missing-workflow",
                "auto-merge control-plane workflow is absent",
                str(WORKFLOW.relative_to(ROOT)),
            ),
        )
    findings = [
        *_workflow_findings(_read(WORKFLOW)),
        *_source_findings(),
        *_cross_file_findings(),
    ]
    return tuple(findings)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    findings = check()
    if findings:
        for finding in findings:
            print(f"::error::{finding.render()}")
        print(f"auto-merge contract: FAIL ({len(findings)} finding(s))")
        return 1
    print(
        "auto-merge contract: OK "
        f"({len(MODULES)} modules, trusted default-branch workflow)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
