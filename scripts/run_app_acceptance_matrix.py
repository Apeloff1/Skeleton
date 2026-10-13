"""Execute reviewed product-family regression candidates at exact checked-out SHA.

This is a CI evidence *producer*, not an independent CI attestation verifier.
Do not import this module from the Jeeves control plane to execute arbitrary
user-directed tests. Only the explicit checked-in matrix selects test modules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from skeleton.ai.game_builder.jeeves_appwide_fabric import AppwideInventory
from skeleton.ai.game_builder.jeeves_acceptance_matrix import JeevesAcceptanceTestMatrix

MAX_SECONDS_PER_MODULE = 120
SCHEMA = "skeleton.ai.app_acceptance_run_evidence.v1"


def _commit(repo):
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, timeout=15, check=True)
    head = result.stdout.strip().lower()
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        raise RuntimeError("unexpected exact-head git identity")
    return head


def _safe_output(value):
    # Do not persist stderr/stdout excerpts: tests can echo secrets or
    # privacy-sensitive fixtures. The digest and byte count are enough to
    # identify the output in the separately secured CI job log.
    encoded = value.encode("utf-8", errors="replace")
    return {"sha256":sha256(encoded).hexdigest(),
            "total_bytes":len(encoded),
            "content_stored_in_artifact":False}


def produce(root: Path, output: Path, *, local=False):
    root = root.resolve()
    if not (root / ".git").exists():
        raise RuntimeError("acceptance tests require a real git checkout")
    head = _commit(root)
    expected = os.environ.get("EXPECTED_SHA", "").strip().lower()
    if not local:
        required = ("CI", "GITHUB_ACTIONS", "GITHUB_RUN_ID", "GITHUB_REPOSITORY",
                    "GITHUB_RUN_ATTEMPT", "GITHUB_WORKFLOW", "EXPECTED_SHA")
        if any(not os.environ.get(k) for k in required):
            raise RuntimeError("independent GitHub Actions metadata missing")
        if not os.environ["GITHUB_REPOSITORY"].endswith("/Skeleton"):
            raise RuntimeError("unexpected repository acceptance authority")
        if expected != head:
            raise RuntimeError("checkout differs from exact PR head")
    elif expected and expected != head:
        raise RuntimeError("local requested SHA does not match checkout")

    inv = AppwideInventory(root)
    inv.scan()
    audit = JeevesAcceptanceTestMatrix(inv).overview()
    results = []
    for module in audit["selected_modules"]:
        start = datetime.now(timezone.utc).isoformat()
        command = [sys.executable, "-m", "unittest", module, "-q"]
        try:
            result = subprocess.run(
                command, cwd=root, capture_output=True, text=True,
                timeout=MAX_SECONDS_PER_MODULE, check=False,
                env={**os.environ, "PYTHONPATH": str(root), "PYTHONUTF8": "1"})
            stdout, stderr = result.stdout, result.stderr
            return_code = result.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(
                exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode("utf-8", "replace") if isinstance(
                exc.stderr, bytes) else (exc.stderr or "")
            return_code = None
            timed_out = True
        results.append({
            "module": module,
            "command": ["python", "-m", "unittest", module, "-q"],
            "started_utc": start,
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "return_code": return_code,
            "timed_out": timed_out,
            "subprocess_executed": True,
            "targeted_tests_passed_in_runner": return_code == 0 and not timed_out,
            "stdout": _safe_output(stdout),
            "stderr": _safe_output(stderr),
            "independent_ci_provenance_verified_by_this_script": False,
        })
        print(f"ACCEPTANCE {module} status={return_code} timeout={timed_out}",flush=True)

    all_pass = len(results) == audit["unique_test_module_count"] and all(
        row["targeted_tests_passed_in_runner"] for row in results)
    body = {
        "schema": SCHEMA,
        "git_head": head,
        "expected_head": expected or None,
        "runner": "Jeeves curated unittest subprocess",
        "local_mode": local,
        "github_claims": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "workflow": os.environ.get("GITHUB_WORKFLOW"),
            "os": os.environ.get("RUNNER_OS"),
        },
        "source_inventory_snapshot": audit["inventory_snapshot"],
        "matrix_digest": audit["digest"],
        "matrix_sha256": audit["matrix_sha256"],
        "scope_sha256": audit["scope_sha256"],
        "test_source_receipts": audit["module_source_receipts"],
        "curated_family_count": audit["curated_test_family_count"],
        "full_family_denominator": audit["family_denominator"],
        "candidate_modules": audit["unique_test_module_count"],
        "modules_actually_executed": len(results),
        "modules_reporting_pass": sum(int(row[
            "targeted_tests_passed_in_runner"]) for row in results),
        "selected_regression_suite_reported_success": all_pass,
        "run_results": results,
        "independent_github_run_identity_verified_externally": False,
        "release_device_verified": False,
        "full_app_completion_percent": None,
        "user_journeys_verified": False,
        "model_weight_promotion_performed": False,
        "product_runtime_source_mutations_performed_by_runner": False,
    }
    payload = json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    stamped = {**body, "receipt_sha256":sha256(payload.encode("utf-8")).hexdigest()}
    # The output is an ephemeral workflow artifact, not a committed source
    # signature. External CI needs to bind its identity separately.
    output = output.resolve()
    if not output.is_relative_to(root):
        raise RuntimeError("acceptance artifact must remain within job workspace")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(stamped,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return all_pass


def main():
    parser=argparse.ArgumentParser(description="source-bound product family test evidence")
    parser.add_argument("--output",default="build/app_acceptance_run_evidence.json")
    parser.add_argument("--local",action="store_true",
                        help="Local smoke only, not independently CI-qualified")
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    passed=produce(root,root/args.output,local=args.local)
    print("Targeted source-bound matrix passed:",passed)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
