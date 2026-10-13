"""Execute actual reviewed pytest families, preserving independent evidence custody.

Only explicit matrix-selected pytest modules are run. Pytest/JUnit test-count
proof is required; zero tests, skips, xfails, errors, malformed XML and
nonzero exits are not accepted. This script produces a CI candidate artifact,
not a CI authentication or installed-product release certificate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from skeleton.ai.game_builder.jeeves_appwide_fabric import AppwideInventory, JeevesAppwideError
from skeleton.ai.game_builder.jeeves_acceptance_matrix import JeevesAcceptanceTestMatrix
from scripts.run_app_acceptance_matrix import _commit, _safe_output

SCHEMA = "skeleton.ai.app_pytest_acceptance_run_evidence.v1"
MAX_SECONDS_PER_MODULE = 180
MAX_XML_BYTES = 2_000_000
MAX_CASES_PER_MODULE = 2000


def _junit_cases(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_XML_BYTES:
        raise JeevesAppwideError("missing or oversized pytest test result")
    content = path.read_bytes()
    if not content or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise JeevesAppwideError("untrusted pytest XML declaration")
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError, RecursionError) as exc:
        raise JeevesAppwideError("invalid pytest JUnit result") from exc
    if root.tag == "testsuites":
        suites = list(root)
        if len(suites) != 1 or suites[0].tag != "testsuite":
            raise JeevesAppwideError("ambiguous pytest JUnit test suite")
        suite = suites[0]
    elif root.tag == "testsuite":
        suite = root
    else:
        raise JeevesAppwideError("unknown pytest JUnit result schema")
    try:
        totals = {key: int(suite.get(key, "-1"))
                  for key in ("tests", "failures", "errors", "skipped")}
    except (ValueError, TypeError, OverflowError) as exc:
        raise JeevesAppwideError("invalid pytest JUnit counters") from exc
    if (not 1 <= totals["tests"] <= MAX_CASES_PER_MODULE
        or any(totals[k] != 0 for k in ("failures", "errors", "skipped"))):
        raise JeevesAppwideError("pytest suite is empty, failed or partially skipped")
    cases = suite.findall("testcase")
    if len(cases) != totals["tests"]:
        raise JeevesAppwideError("pytest JUnit count and actual test cases disagree")
    for row in cases:
        if (type(row.get("name")) is not str or not row.get("name") or
            type(row.get("classname")) is not str or not row.get("classname") or
            any(child.tag in ("failure", "error", "skipped") for child in row)):
            raise JeevesAppwideError("invalid or unsuccessful pytest test case")
    return {
        "cases_executed": len(cases),
        "cases_failed": 0,
        "cases_errored": 0,
        "cases_skipped": 0,
        "xml_sha256": sha256(content).hexdigest(),
        "tests_run_in_real_pytest": True,
    }


def produce(root: Path, output: Path, *, local: bool = False) -> bool:
    root = root.resolve()
    if not (root / ".git").exists():
        raise JeevesAppwideError("real exact-head repository checkout required")
    head = _commit(root)
    expected_head = os.environ.get("EXPECTED_SHA", "").lower().strip()
    if not local:
        required = {
            "CI": "true",
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "Apeloff1/Skeleton",
            "GITHUB_WORKFLOW": "Jeeves App Pytest Acceptance",
        }
        if any(os.environ.get(k, "").lower() != v.lower()
               for k, v in required.items()):
            raise JeevesAppwideError("invalid GitHub Actions workflow provenance claims")
        if (not os.environ.get("GITHUB_RUN_ID", "").isdigit() or
            not os.environ.get("GITHUB_RUN_ATTEMPT", "").isdigit() or
            os.environ.get("RUNNER_OS") not in ("Linux", "Windows")):
            raise JeevesAppwideError("invalid exact CI job identity")
        if not expected_head or expected_head != head:
            raise JeevesAppwideError("CI checkout differs from reviewed exact head")
    elif expected_head and expected_head != head:
        raise JeevesAppwideError("local exact SHA is stale")

    inv = AppwideInventory(root)
    inv.scan()
    projection = JeevesAcceptanceTestMatrix(inv).overview()
    modules = projection["pytest_selected_modules"]
    if not modules or len(modules) != projection["scheduled_pytest_module_count"]:
        raise JeevesAppwideError("unreviewed or empty pytest acceptance module selection")
    if set(modules) & set(projection["selected_modules"]):
        raise JeevesAppwideError("same module selected by incompatible test runners")
    rows = []
    with TemporaryDirectory(prefix="jeeves-pytest-acceptance-") as temp:
        scratch = Path(temp)
        for index, module in enumerate(modules):
            xml_path = scratch / ("module_%02d.xml" % index)
            started = datetime.now(timezone.utc).isoformat()
            target = module.replace(".", "/") + ".py"
            argv = [
                sys.executable, "-m", "pytest",
                "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                "--junitxml=" + str(xml_path), target,
            ]
            try:
                run = subprocess.run(
                    argv, cwd=root, capture_output=True, text=True,
                    timeout=MAX_SECONDS_PER_MODULE, check=False,
                    env={**os.environ, "PYTHONPATH": str(root),
                         "PYTHONUTF8": "1",
                         "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
                )
                return_code = run.returncode
                output_text = run.stdout
                error_text = run.stderr
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                return_code = None
                output_text = exc.stdout or ""
                error_text = exc.stderr or ""
                if isinstance(output_text, bytes):
                    output_text = output_text.decode("utf-8", "replace")
                if isinstance(error_text, bytes):
                    error_text = error_text.decode("utf-8", "replace")
                timed_out = True
            observation = None
            if return_code == 0 and not timed_out:
                try:
                    observation = _junit_cases(xml_path)
                except JeevesAppwideError:
                    observation = None
            valid = return_code == 0 and not timed_out and observation is not None
            rows.append({
                "module": module,
                "command": ["python", "-m", "pytest", "-q",
                            "-p", "no:cacheprovider", "-o", "addopts=", target],
                "started_utc": started,
                "ended_utc": datetime.now(timezone.utc).isoformat(),
                "return_code": return_code,
                "timed_out": timed_out,
                "subprocess_executed": True,
                "pytest_cases_observed": observation["cases_executed"] if observation else None,
                "junit_xml_sha256": observation["xml_sha256"] if observation else None,
                "targeted_tests_passed_in_runner": bool(valid),
                "stdout": _safe_output(output_text),
                "stderr": _safe_output(error_text),
                "independent_ci_provenance_verified_by_this_script": False,
            })
            print(f"PYTEST-ACCEPTANCE {module} passed={valid} cases=" +
                  str(rows[-1]["pytest_cases_observed"]), flush=True)
    all_pass = (len(rows) == len(modules) and all(
        row["targeted_tests_passed_in_runner"] for row in rows))
    payload = {
        "schema": SCHEMA,
        "git_head": head,
        "expected_head": expected_head or None,
        "local_mode": local,
        "runner": "reviewed pytest JUnit XML subprocess",
        "github_claims": {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "workflow": os.environ.get("GITHUB_WORKFLOW"),
            "os": os.environ.get("RUNNER_OS"),
        },
        "source_inventory_snapshot": projection["inventory_snapshot"],
        "matrix_digest": projection["digest"],
        "matrix_sha256": projection["matrix_sha256"],
        "scope_sha256": projection["scope_sha256"],
        "test_source_receipts": projection["module_source_receipts"],
        "pytest_family_count": projection["pytest_smoke_family_count"],
        "full_family_denominator": projection["family_denominator"],
        "candidate_modules": len(modules),
        "modules_actually_executed": len(rows),
        "modules_reporting_pass": sum(int(x["targeted_tests_passed_in_runner"])
                                      for x in rows),
        "pytest_cases_observed_total": sum(x["pytest_cases_observed"] or 0 for x in rows),
        "selected_regression_suite_reported_success": all_pass,
        "run_results": rows,
        "independent_github_run_identity_verified_externally": False,
        "release_device_verified": False,
        "user_journeys_verified": False,
        "full_app_completion_percent": None,
        "model_weight_promotion_performed": False,
        "product_runtime_source_mutations_performed_by_runner": False,
    }
    stamp = sha256(json.dumps(payload, sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    artifact = {**payload, "receipt_sha256": stamp}
    output = output.resolve()
    if not output.is_relative_to(root):
        raise JeevesAppwideError("CI acceptance artifact must be inside job workspace")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    return all_pass


def main():
    parser = argparse.ArgumentParser(
        description="Execute exactly reviewed pytest acceptance subsets")
    parser.add_argument("--output", default="build/app_pytest_acceptance_run_evidence.json")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    return 0 if produce(root, root / args.output, local=args.local) else 1


if __name__ == "__main__":
    raise SystemExit(main())
