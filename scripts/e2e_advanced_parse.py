#!/usr/bin/env python3
"""No-execution static E2E inventory, dependency/risk parse and gap report."""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATHS = ("tests", "skeleton/testing", "backend/tests", "frontend/scripts", "frontend/__tests__", ".github/workflows")
SIGNALS = {
    "network": r"\b(?:requests|httpx|urllib|fetch|axios|aiohttp)\b|https?://localhost",
    "process": r"\b(?:subprocess|Popen|os\.system|spawn|child_process)\b",
    "mutation": r"\b(?:unlink|rmtree|write_text|write_bytes|rmSync)\b",
    "database": r"\b(?:mongo|sqlite|redis|postgres|chroma)\b",
    "skip": r"\b(?:pytest\.skip|pytest\.xfail|mark\.skip|mark\.xfail)\b",
    "provider": r"\b(?:openai|anthropic|LLM|inference)\b",
}
DOMAINS = {
    "AI/Jeeves": ("jeeves", "ai_chat", "conversation", "model", "inference"),
    "game/forge": ("game", "forge", "rpg", "playable", "world"),
    "backend/API": ("api", "route", "service", "backend"),
    "frontend": ("frontend", "browser", "webview", "screen"),
    "durability": ("mongo", "sqlite", "storage", "repository", "durable"),
    "recovery": ("restart", "rollback", "crash", "retry", "fault"),
    "security": ("security", "authority", "governance", "tenant"),
    "release": ("build", "deploy", "install", "assembly", "artifact"),
}

def tracked():
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--", *PATHS], cwd=ROOT,
                           capture_output=True, timeout=20, check=True)
        return sorted(set(x.decode("utf-8", "replace") for x in r.stdout.split(b"\0") if x))
    except (OSError, subprocess.SubprocessError):
        return sorted(set(p.relative_to(ROOT).as_posix() for d in PATHS
                          for p in (ROOT / d).rglob("*") if p.is_file()))

def issue(out, path, kind, severity, detail):
    uid = hashlib.sha256((path + "|" + kind).encode()).hexdigest()[:16].upper()
    out.append({"id": "E2EPARSE-" + uid, "status": "needs-triage", "path": path,
                "kind": kind, "severity": severity, "detail": detail})

def examine(path, live, issues):
    file = ROOT / path
    name = file.name
    if not path.endswith((".py", ".mjs", ".cjs", ".js", ".ts", ".tsx")) or not (
        name.startswith("test") or name.endswith((".test.cjs", ".test.mjs", ".test.js", ".test.ts", ".test.tsx", ".spec.ts"))
    ):
        return None
    try:
        if file.stat().st_size > 1024 * 1024:
            issue(issues, path, "oversize-test", "medium", "Source exceeds parser bound")
            return None
        body = file.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        issue(issues, path, "unreadable-test", "high", "Cannot inspect source")
        return None
    marked = False
    if path.endswith(".py"):
        try:
            tree = ast.parse(body, filename=path)
        except SyntaxError as error:
            issue(issues, path, "syntax-error", "high", "AST error at line " + str(error.lineno))
            return None
        count = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
                    for n in ast.walk(tree))
        marked = any(isinstance(n, ast.Attribute) and n.attr == "live_service" and
                     isinstance(n.value, ast.Attribute) and n.value.attr == "mark"
                     for n in ast.walk(tree))
    else:
        count = len(re.findall(r"\b(?:test|it)\s*\(\s*['\"]", body))
    flags = sorted(k for k, pattern in SIGNALS.items() if re.search(pattern, body, re.I))
    registered = path.startswith("backend/tests/") and name in live
    if marked and not registered and path.startswith("backend/tests/"):
        issue(issues, path, "unregistered-live-service", "high", "Live marker absent from registry")
    if registered and not marked:
        issue(issues, path, "missing-live-service-marker", "high", "Registry entry lacks module marker")
    if "network" in flags and not (marked or registered):
        issue(issues, path, "network-tier-review", "medium", "Inspect whether HTTP signature is test fixture or live IO")
    if "skip" in flags:
        issue(issues, path, "skip-review", "low", "Check that skips/xfails have owners and reasons")
    risk = ("high" if marked or registered else
            "review" if any(f in flags for f in ("network", "process", "database", "mutation"))
            else "low")
    return {"path": path, "sha256": hashlib.sha256(body.encode()).hexdigest(),
            "named_test_count_estimate": count,
            "tier": "live" if marked or registered else "offline-candidate",
            "risk": risk, "signals": flags,
            "domains": sorted(k for k, words in DOMAINS.items()
                              if any(w in path.lower() for w in words))}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=ROOT / ".e2e-evidence")
    args = p.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    findings = []
    paths = tracked()
    if not paths:
        issue(findings, "repository", "empty-inventory", "critical", "No source inventory")
    if len(paths) > 15000:
        issue(findings, "repository", "truncated-inventory", "critical", "Exceeded 15000 inventory entries")
        paths = paths[:15000]
    try:
        live = set(json.loads((ROOT / "backend/tests/live_service_tests.json")
                              .read_text(encoding="utf-8"))["tests"])
    except (OSError, KeyError, ValueError, TypeError):
        live = set()
        issue(findings, "backend/tests/live_service_tests.json", "invalid-registry",
              "critical", "Unable to parse live-service registry")
    suites = []
    for path in paths:
        item = examine(path, live, findings)
        if item:
            suites.append(item)
        if path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")):
            try:
                body = (ROOT / path).read_text(encoding="utf-8")[:1024 * 1024]
            except (OSError, UnicodeError):
                continue
            if any(t in body for t in ("pytest", "node --test", "golden journey")):
                if "upload-artifact" not in body:
                    issue(findings, path, "missing-artifact-upload-review", "low",
                          "Test workflow may not persist JUnit and failure diagnostics")
    priorities = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    candidates = sorted({x["id"]: x for x in findings}.values(),
                        key=lambda x: (priorities[x["severity"]], x["path"]))
    report = {"schema": "skeleton.e2e.static_inventory.v1",
              "utc": datetime.now(timezone.utc).isoformat(),
              "head_sha": os.environ.get("E2E_HEAD_SHA", "unbound")[:40],
              "paths_inspected": len(paths), "test_modules": len(suites),
              "test_functions_estimate": sum(x["named_test_count_estimate"] for x in suites),
              "risks": dict(Counter(x["risk"] for x in suites)),
              "domains": dict(Counter(d for x in suites for d in x["domains"])),
              "issue_candidates": candidates, "suites": suites}
    (output / "advanced-parse.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = ["# Static E2E inventory", "",
             "- Exact head: " + report["head_sha"],
             "- Test modules: " + str(len(suites)),
             "- Named test functions estimated: " + str(report["test_functions_estimate"]),
             "- Issues needing triage: " + str(len(candidates)),
             "", "## Domains"]
    lines.extend("- " + name + ": " + str(n) for name, n in sorted(report["domains"].items()))
    lines.extend(["", "## Risk candidates", "", "| ID | Priority | Finding | File |", "| --- | --- | --- | --- |"])
    lines.extend("| " + x["id"] + " | " + x["severity"] + " | " + x["kind"] + " | " +
                 x["path"] + " |" for x in candidates[:180])
    lines.extend(["", "Static signals are review candidates, not confirmed defects or test-pass evidence.", ""])
    (output / "advanced-parse.md").write_text("\n".join(lines))
    print("E2E static scan: " + str(len(suites)) + " modules; " + str(len(candidates)) + " candidates")
    return 2 if any(x["severity"] == "critical" for x in candidates) else 0

if __name__ == "__main__":
    raise SystemExit(main())
