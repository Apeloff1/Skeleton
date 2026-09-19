"""Static contract gate for the privileged PR automation runner-v2 surface."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skeleton" / "pr_automation"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-automation-index.yml"
LEGACY_RUNNER = PACKAGE / "runner.py"
MODULES = (
    "runner_contracts.py",
    "runner_transport.py",
    "runner_evidence.py",
    "runner_targeting.py",
    "runner_scheduler.py",
    "runner_transaction.py",
    "runner_report.py",
    "runner_engine.py",
    "runner_v2_cli.py",
)
REQUIRED_WORKFLOW_PERMISSIONS = {
    "actions": "read",
    "checks": "read",
    "contents": "write",
    "pull-requests": "write",
    "statuses": "write",
}
FORBIDDEN_IMPORTS = {
    "subprocess",
    "socket",
    "pty",
    "telnetlib",
    "ftplib",
    "paramiko",
    "requests",
}
FORBIDDEN_SOURCE_MARKERS = (
    "eval(",
    "exec(",
    "__import__(",
    "os.system(",
    "shell=True",
)
REQUIRED_V2_MARKERS = {
    "runner_transport.py": (
        "class BudgetedGitHubTransport",
        "RequestBudgetExceeded",
        "UnsafeMutationRetry",
    ),
    "runner_evidence.py": (
        "class EvidenceCollector",
        "exact_base_head",
        "required_check_states",
    ),
    "runner_targeting.py": (
        "class TargetResolver",
        "head_sha",
        "same_repo_head",
    ),
    "runner_scheduler.py": (
        "class MutableBudget",
        "budget_allows_mutation",
        "score_work_item",
    ),
    "runner_transaction.py": (
        "class MergeTransaction",
        "expected_head_sha",
        "compute_transaction_preconditions",
    ),
    "runner_report.py": (
        "assert_report_invariants",
        "checkpoint_from_report",
        "markdown_summary",
    ),
    "runner_engine.py": (
        "class RunnerEngine",
        "append_evaluation_event",
        "MergeTransaction",
    ),
    "runner_v2_cli.py": (
        "runner_policy_from_env",
        "run_engine",
        "PR_AUTOMATION_MODE",
        "load_operator_safety",
    ),
}


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result


def _line_block(text: str, header: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        indent = len(line) - len(line.lstrip())
        block = [line]
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                block.append(candidate)
                continue
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate_indent <= indent:
                break
            block.append(candidate)
        return "\n".join(block)
    return ""


def _module_findings(path: Path) -> list[str]:
    findings: list[str] = []
    if not path.is_file():
        return [f"missing module: {path.relative_to(ROOT)}"]
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [
            f"syntax error in {path.relative_to(ROOT)}:"
            f"{exc.lineno}:{exc.offset}: {exc.msg}"
        ]

    imported = _imports(tree)
    bad_imports = sorted(imported.intersection(FORBIDDEN_IMPORTS))
    if bad_imports:
        findings.append(
            f"{path.name} imports forbidden execution packages: "
            + ",".join(bad_imports)
        )
    for marker in FORBIDDEN_SOURCE_MARKERS:
        if marker in source:
            findings.append(f"{path.name} contains forbidden marker {marker!r}")

    for marker in REQUIRED_V2_MARKERS.get(path.name, ()):
        if marker not in source:
            findings.append(
                f"{path.name} missing required runner-v2 marker {marker!r}"
            )
    return findings


def _workflow_findings(text: str) -> list[str]:
    findings: list[str] = []
    if "pull_request_target:" in text:
        findings.append("workflow must not use pull_request_target")
    if 'PR_AUTOMATION_RUNNER_V2: "true"' not in text:
        findings.append("workflow does not explicitly enable runner v2")
    trusted_ref = "ref: " + "$" + "{{ github.event.repository.default_branch }}"
    if trusted_ref not in text:
        findings.append("workflow must checkout trusted default branch")
    if "persist-credentials: false" not in text:
        findings.append("trusted checkout must disable credential persistence")
    if "cancel-in-progress: false" not in text:
        findings.append("runner concurrency must be non-preemptive")

    evaluate = _line_block(text, "evaluate:")
    permissions = _line_block(evaluate, "permissions:")
    if not evaluate:
        findings.append("workflow missing evaluate job")
    for name, value in REQUIRED_WORKFLOW_PERMISSIONS.items():
        if f"{name}: {value}" not in permissions:
            findings.append(
                f"evaluate permissions missing {name}: {value}"
            )

    required_markers = (
        "python -I -c",
        "TRUSTED_PR_AUTOMATION_ROOT",
        "actions/cache/restore@",
        "actions/cache/save@",
        ".pr-automation/runner-report.json",
        ".pr-automation/runner-transport.json",
        ".pr-automation/runner-checkpoint.json",
        'PR_RUNNER_REQUIRE_EXACT_BASE_HEAD: "true"',
        'PR_RUNNER_REQUIRE_PROTECTED_BASE: "true"',
        'PR_RUNNER_REQUIRE_SAME_REPOSITORY_HEAD: "true"',
        'PR_RUNNER_REQUIRE_LATEST_REVIEWS_ON_HEAD: "true"',
    )
    for marker in required_markers:
        if marker not in text:
            findings.append(f"workflow missing required marker {marker!r}")
    return findings


def _legacy_findings(source: str) -> list[str]:
    findings: list[str] = []
    if "PR_AUTOMATION_RUNNER_V2" not in source:
        findings.append("legacy runner is missing v2 feature switch")
    if "from .runner_v2_cli import run_v2" not in source:
        findings.append("legacy runner does not route to canonical v2 CLI")
    if "return run_v2(argv)" not in source:
        findings.append("legacy runner does not delegate argv unchanged")
    return findings


def _cross_file_findings() -> list[str]:
    findings: list[str] = []
    contracts = (PACKAGE / "runner_contracts.py").read_text(encoding="utf-8")
    transaction = (PACKAGE / "runner_transaction.py").read_text(encoding="utf-8")
    engine = (PACKAGE / "runner_engine.py").read_text(encoding="utf-8")
    transport = (PACKAGE / "runner_transport.py").read_text(encoding="utf-8")
    evidence = (PACKAGE / "runner_evidence.py").read_text(encoding="utf-8")

    checks = (
        (
            "expected_head_sha" in contracts
            and "expected_base_sha" in contracts,
            "mutation intent lacks expected head/base identity",
        ),
        (
            '"sha": intent.expected_head_sha' in transaction,
            "merge mutation is not server-bound to expected head SHA",
        ),
        (
            "retry_safe=False" in transaction,
            "merge mutation must explicitly disable transport retry",
        ),
        (
            "collector.refresh_policy_fields" in transaction,
            "transaction must refresh mutation-grade evidence",
        ),
        (
            "branch_protected(" in transaction,
            "transaction must re-read protected base state",
        ),
        (
            "branch_head(" in transaction,
            "transaction must re-read base head",
        ),
        (
            "index.claim_action(" in transaction,
            "transaction must use durable idempotency claim",
        ),
        (
            "assert_report_invariants(report)" in engine,
            "engine must assert final report invariants",
        ),
        (
            "max_response_bytes" in transport,
            "transport must retain response-size bound",
        ),
        (
            "max_requests" in transport,
            "transport must retain request budget",
        ),
        (
            "max_graphql_requests" in transport,
            "transport must retain GraphQL budget",
        ),
        (
            "same_repository_head" in evidence,
            "evidence must preserve head repository identity",
        ),
        (
            "base_head_sha" in evidence,
            "evidence must preserve observed base head",
        ),
    )
    for ok, message in checks:
        if not ok:
            findings.append(message)
    return findings


def check() -> tuple[str, ...]:
    findings: list[str] = []
    if not WORKFLOW.is_file():
        findings.append("missing PR automation workflow")
    else:
        findings.extend(
            _workflow_findings(WORKFLOW.read_text(encoding="utf-8"))
        )

    if not LEGACY_RUNNER.is_file():
        findings.append("missing legacy runner compatibility shim")
    else:
        findings.extend(
            _legacy_findings(LEGACY_RUNNER.read_text(encoding="utf-8"))
        )

    for name in MODULES:
        findings.extend(_module_findings(PACKAGE / name))

    if all((PACKAGE / name).is_file() for name in MODULES):
        findings.extend(_cross_file_findings())

    return tuple(dict.fromkeys(findings))


def main() -> int:
    findings = check()
    if findings:
        for finding in findings:
            print(f"runner-v2-contract: {finding}")
        return 1
    print("runner-v2-contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
