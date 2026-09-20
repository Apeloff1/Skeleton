"""Repository-wide fail-closed contract manifest.

This gate composes the repository's privileged static contract checkers into one
bounded, deterministic entry point. It does not replace subsystem tests: it
ensures contract gates cannot silently disappear, stop compiling, or stop being
wired into Merge Readiness.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.contracts.system_catalog import (
    CATALOG,
    audit_catalog,
    authority_paths,
    contract_fingerprints,
    topological_order,
    validate_authority_paths,
    validate_catalog,
)

MAX_CHECKER_BYTES = 300_000
MAX_SECONDS_PER_CHECKER = 90
CHECKERS = tuple(spec.checker for spec in topological_order(CATALOG))
REQUIRED_WIRING = (
    "python scripts/check_contract_system.py",
)
FORBIDDEN_CALLS = frozenset({"eval", "exec", "os.system"})


@dataclass(frozen=True, slots=True)
class ContractEvidence:
    path: str
    sha256: str
    bytes: int
    returncode: int
    stdout_tail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "returncode": self.returncode,
            "stdout_tail": self.stdout_tail,
        }


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return ""


def _forbidden_execution_marker(tree: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        if call_name in FORBIDDEN_CALLS:
            return call_name
        for keyword in node.keywords:
            if (
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                return f"{call_name or '<dynamic>'}(shell=True)"
    return None


def _admit_checker(relative: str) -> tuple[Path, bytes]:
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"contract checker missing or symlinked: {relative}")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_CHECKER_BYTES or b"\x00" in raw:
        raise RuntimeError(f"contract checker has invalid bounded content: {relative}")
    try:
        source = raw.decode("utf-8")
        tree = ast.parse(source, filename=relative)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise RuntimeError(f"contract checker is not valid UTF-8 Python: {relative}") from exc
    marker = _forbidden_execution_marker(tree)
    if marker is not None:
        raise RuntimeError(f"contract checker contains forbidden execution call {marker!r}: {relative}")
    return path, raw


def _run_checker(relative: str) -> ContractEvidence:
    path, raw = _admit_checker(relative)
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=MAX_SECONDS_PER_CHECKER,
        check=False,
    )
    tail = proc.stdout[-4000:]
    return ContractEvidence(
        path=relative,
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw),
        returncode=proc.returncode,
        stdout_tail=tail,
    )


def _validate_manifest() -> None:
    validate_catalog(CATALOG)
    audit = audit_catalog(CATALOG)
    validate_authority_paths(CATALOG)
    if not audit.clean:
        raise RuntimeError(
            "cross-contract consistency failure: "
            f"ownership={audit.ownership_conflicts!r} "
            f"orphans={audit.orphan_dependencies!r} "
            f"privilege_escalations={audit.privilege_escalations!r}"
        )
    if len(CHECKERS) != len(set(CHECKERS)):
        raise RuntimeError("duplicate checker in contract manifest")
    for relative in CHECKERS:
        if not relative.startswith("scripts/check_") or not relative.endswith("_contract.py"):
            raise RuntimeError(f"non-canonical contract checker path: {relative}")


def _validate_wiring() -> None:
    workflow = (ROOT / ".github/workflows/merge-readiness.yml").read_text(encoding="utf-8")
    for marker in REQUIRED_WIRING:
        if marker not in workflow:
            raise RuntimeError(f"merge-readiness missing contract-system wiring: {marker}")


def main() -> int:
    _validate_manifest()
    _validate_wiring()
    evidence: list[ContractEvidence] = []
    failed = False
    for checker in CHECKERS:
        try:
            item = _run_checker(checker)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"contract-system: FAIL {checker}: {exc}", file=sys.stderr)
            failed = True
            continue
        evidence.append(item)
        status = "PASS" if item.returncode == 0 else "FAIL"
        print(f"contract-system: {status} {item.path} sha256={item.sha256} bytes={item.bytes}")
        if item.returncode:
            failed = True
            if item.stdout_tail:
                print(item.stdout_tail, file=sys.stderr)
    summary = {
        "version": 2,
        "catalog_digest": hashlib.sha256(json.dumps([
            {
                "id": spec.contract_id,
                "checker": spec.checker,
                "tier": spec.tier.value,
                "depends_on": spec.depends_on,
                "owns": spec.owns,
                "evidence_version": spec.evidence_version,
                "consumes_evidence": spec.consumes_evidence,
                "privileges": spec.privileges,
                "maturity": spec.maturity,
                "supersedes": spec.supersedes,
            }
            for spec in topological_order(CATALOG)
        ], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "execution_order": [spec.contract_id for spec in topological_order(CATALOG)],
        "dependency_edges": sorted(
            [dependency, spec.contract_id]
            for spec in CATALOG
            for dependency in spec.depends_on
        ),
        "evidence_compatibility": {
            spec.contract_id: {
                producer: version
                for producer, version in spec.consumes_evidence
            }
            for spec in sorted(CATALOG, key=lambda item: item.contract_id)
        },
        "contract_fingerprints": contract_fingerprints(CATALOG),
        "authority_paths": {
            spec.contract_id: [list(path) for path in authority_paths(spec.contract_id, CATALOG)]
            for spec in sorted(CATALOG, key=lambda item: item.contract_id)
        },
        "lifecycle": {
            spec.contract_id: {
                "maturity": spec.maturity,
                "supersedes": list(spec.supersedes),
            }
            for spec in sorted(CATALOG, key=lambda item: item.contract_id)
        },
        "privileges": {
            spec.contract_id: list(spec.privileges)
            for spec in sorted(CATALOG, key=lambda item: item.contract_id)
        },
        "ownership": {
            spec.contract_id: list(spec.owns)
            for spec in sorted(CATALOG, key=lambda item: item.contract_id)
        },
        "checker_count": len(CHECKERS),
        "executed_count": len(evidence),
        "failed_count": sum(item.returncode != 0 for item in evidence) + (len(CHECKERS) - len(evidence)),
        "evidence": [item.as_dict() for item in evidence],
    }
    print("contract-system-evidence=" + json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
