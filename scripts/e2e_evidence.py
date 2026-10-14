#!/usr/bin/env python3
"""Fail-closed, metadata-first E2E evidence recorder.

Preflight does not run tests. Execution is an explicit, separate opt-in.
Every invocation emits a timestamped event stream, a reproducible suite ledger,
a redacted command log, issue records, and a human-readable summary.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "machine" / "e2e_suites.json"
MAX_LINE = 4096
MAX_LINES = 10000
SUITE_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def redactor():
    # Load the existing canonical redaction primitive without initializing the
    # entire runtime dependency graph during a stdlib-only preflight.
    source = ROOT / "skeleton" / "observability" / "redaction.py"
    spec = importlib.util.spec_from_file_location("_e2e_canonical_redaction", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical telemetry redaction is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.redact_text


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class Recorder:
    def __init__(self, output: Path, redact):
        self.output = output
        self.output.mkdir(parents=True, exist_ok=True)
        self.redact = redact
        self.events = (output / "events.jsonl").open("w", encoding="utf-8")
        self.issues: list[dict] = []
        self.suites: list[dict] = []
        self.test_counts: dict[str, dict] = {}
        self.started = timestamp()
        self.run_id = digest(self.started + ":" + os.environ.get("GITHUB_RUN_ID", "local"))

    def emit(self, event_name: str, **metadata):
        # Never accept arbitrary credential-bearing objects in event metadata.
        safe = {key: self.redact(str(value))[:MAX_LINE] for key, value in metadata.items()}
        event = {"timestamp": timestamp(), "run_id": self.run_id, "event": event_name, **safe}
        self.events.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
        self.events.flush()

    def issue(self, *, suite: str, phase: str, kind: str, message: str,
              testcase: str = "", evidence: str = "", severity: str = "high"):
        signature = digest("|".join((suite, phase, kind, testcase)))
        entry = {
            "id": f"E2E-{signature.upper()}",
            "severity": severity,
            "status": "open",
            "suite": suite,
            "phase": phase,
            "kind": kind,
            "testcase": self.redact(testcase)[:500],
            "summary": self.redact(message)[:1200],
            "evidence": evidence,
            "head_sha": os.environ.get("E2E_HEAD_SHA", os.environ.get("GITHUB_SHA", "local"))[:40],
            "first_observed_utc": timestamp(),
        }
        if not any(item["id"] == entry["id"] for item in self.issues):
            self.issues.append(entry)
            self.emit("issue.opened", issue_id=entry["id"], suite=suite, kind=kind)
        return entry

    def finish(self, mode: str) -> None:
        failed = sum(item["status"] not in ("passed", "not_run") for item in self.suites)
        result = {
            "schema": "skeleton.e2e.evidence.v1",
            "run_id": self.run_id,
            "mode": mode,
            "started_utc": self.started,
            "finished_utc": timestamp(),
            "head_sha": os.environ.get("E2E_HEAD_SHA", os.environ.get("GITHUB_SHA", "local"))[:40],
            "python": platform.python_version(),
            "platform": platform.system().lower(),
            "status": "failed" if self.issues or failed else "ready" if mode == "preflight" else "passed",
            "executed_suites": sum(item["status"] in ("passed", "failed") for item in self.suites),
            "issues_count": len(self.issues),
            "suites": self.suites,
        }
        (self.output / "report.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.output / "issues.json").write_text(
            json.dumps({"schema": "skeleton.e2e.issues.v1", "issues": self.issues},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        lines = [
            "# E2E evidence and issue ledger",
            "",
            f"- Run: {self.run_id}",
            f"- Exact head: {result['head_sha']}",
            f"- Mode: {mode}",
            f"- Result: **{result['status']}**",
            f"- Suites executed: {result['executed_suites']}",
            f"- Issues: **{len(self.issues)}**",
            "",
            "## Suite dispositions",
            "",
            "| Suite | Result | Duration (s) | Evidence |",
            "| --- | --- | ---: | --- |",
        ]
        for item in self.suites:
            lines.append(
                f"| {item['id']} | {item['status']} | {item['duration_seconds']:.2f} "
                f"| {item.get('log', 'not executed')} |"
            )
        lines += ["", "## Issues", ""]
        if self.issues:
            for item in self.issues:
                lines += [
                    f"### {item['id']} · {item['kind']}",
                    "",
                    f"- Severity: {item['severity']}",
                    f"- Suite/test: {item['suite']} / {item['testcase'] or 'suite startup'}",
                    f"- Summary: {item['summary']}",
                    f"- Evidence: {item['evidence'] or 'report.json'}",
                    f"- Exact head: {item['head_sha']}",
                    "- Disposition: open; reproduce at this head, assign owner, link fix PR and retest receipt",
                    "",
                ]
        else:
            lines.append("No issues observed in the executed scope; unexecuted journeys remain unverified.")
        lines += ["", "No live service or provider test runs in preflight mode.", ""]
        summary = "\n".join(lines)
        (self.output / "issues.md").write_text(summary, encoding="utf-8")
        (self.output / "summary.md").write_text(summary, encoding="utf-8")
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as handle:
                handle.write(summary[:40000] + "\n")
        self.emit("run.finished", result=result["status"], issues=len(self.issues))
        self.events.close()


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("E2E suite manifest requires version 1")
    suites = payload.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("suite inventory is empty")
    seen = set()
    for item in suites:
        if not isinstance(item, dict):
            raise ValueError("suite entry must be an object")
        name = item.get("id")
        if not isinstance(name, str) or not SUITE_ID.fullmatch(name) or name in seen:
            raise ValueError("suite IDs must be unique filesystem-safe names")
        seen.add(name)
        if item.get("tier") not in ("offline", "live"):
            raise ValueError(f"{name}: unrecognized execution tier")
        cmd = item.get("command")
        if not isinstance(cmd, list) or not cmd or not all(
            isinstance(arg, str) and arg and "\0" not in arg for arg in cmd
        ):
            raise ValueError(f"{name}: command must be non-empty argv")
        if cmd[0] not in ("python", "node"):
            raise ValueError(f"{name}: unsupported executable")
        cwd = item.get("cwd")
        paths = item.get("required_files")
        if not isinstance(cwd, str) or not isinstance(paths, list):
            raise ValueError(f"{name}: cwd and required_files are mandatory")
        for rel in [cwd, *paths]:
            if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise ValueError(f"{name}: unsafe repository path")
        if not isinstance(item.get("timeout_seconds"), int) or not 1 <= item["timeout_seconds"] <= 3600:
            raise ValueError(f"{name}: invalid bounded timeout")
    return suites


def check_inventory(rec: Recorder, suites: list[dict]) -> None:
    for item in suites:
        missing = [
            rel for rel in [item["cwd"], *item["required_files"]]
            if not (ROOT / rel).exists()
        ]
        status = "blocked" if missing else "not_run"
        rec.suites.append({"id": item["id"], "status": status, "duration_seconds": 0.0})
        rec.emit("suite.preflight", suite=item["id"], status=status,
                 tier=item["tier"], file_count=len(item["required_files"]))
        for rel in missing:
            rec.issue(suite=item["id"], phase="preflight", kind="missing-file",
                      message=f"Required repository path is absent: {rel}",
                      evidence="machine/e2e_suites.json")
    rec.emit("preflight.completed", inventoried=len(suites), issues=len(rec.issues))


def parse_junit(path: Path, suite: str, rec: Recorder) -> int:
    if not path.exists():
        rec.issue(suite=suite, phase="execute", kind="missing-junit",
                  message="Pytest did not produce an XML test receipt",
                  evidence=f"logs/{suite}.log")
        return 0
    try:
        xml = ET.parse(path)
    except (ET.ParseError, OSError):
        rec.issue(suite=suite, phase="execute", kind="malformed-junit",
                  message="Pytest XML receipt is unreadable or malformed",
                  evidence=f"logs/{suite}.log")
        return 0
    problems = 0
    counts = {"collected": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0}
    for case in xml.iter("testcase"):
        counts["collected"] += 1
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        passed = True
        for tag in ("failure", "error"):
            for finding in case.findall(tag):
                passed = False
                counts["failures" if tag == "failure" else "errors"] += 1
                problems += 1
                message = finding.get("message") or finding.text or tag
                rec.issue(suite=suite, phase="execute", kind=tag, testcase=name,
                          message=message[:1200], evidence=f"junit/{suite}.xml")
        for finding in case.findall("skipped"):
            passed = False
            counts["skipped"] += 1
            problems += 1
            rec.issue(suite=suite, phase="execute", kind="unverified-test", testcase=name,
                      message=finding.get("message") or "Skipped or expected-failure test was not verified",
                      severity="medium", evidence=f"junit/{suite}.xml")
        counts["passed"] += int(passed)
    if not counts["collected"]:
        problems += 1
        rec.issue(suite=suite, phase="execute", kind="empty-junit",
                  message="The XML receipt contains no test cases", evidence=f"junit/{suite}.xml")
    rec.test_counts[suite] = counts
    rec.emit("suite.test-counts", suite=suite, **counts)
    # JUnit can include arbitrary failure text. The artifact must never retain
    # the raw XML that pytest emitted.
    for node in xml.iter():
        for key, value in node.attrib.items():
            node.set(key, rec.redact(value)[:MAX_LINE])
        if node.text:
            node.text = rec.redact(node.text)[:20000]
        if node.tail:
            node.tail = rec.redact(node.tail)[:MAX_LINE]
    target = rec.output / "junit" / f"{suite}.xml"
    target.parent.mkdir(exist_ok=True)
    xml.write(target, encoding="utf-8", xml_declaration=True)
    path.unlink(missing_ok=True)
    return problems


def launch(rec: Recorder, suite: dict) -> None:
    name = suite["id"]
    logfile = rec.output / "logs" / f"{name}.log"
    logfile.parent.mkdir(exist_ok=True)
    cmd = list(suite["command"])
    private_xml = None
    if cmd[0] == "python":
        cmd[0] = sys.executable
        if "-m" in cmd and "pytest" in cmd:
            private_xml = rec.output / f".{name}.raw.xml"
            cmd += [f"--junitxml={private_xml}", "--durations=20"]
    # No shell, no user-controlled command and no provider credentials.
    allowed_env = ("PATH", "HOME", "LANG", "LC_ALL", "CI", "PYTHONPATH",
                   "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "VIRTUAL_ENV",
                   "GITHUB_ACTIONS", "TMPDIR", "NODE_OPTIONS")
    env = {key: os.environ[key] for key in allowed_env if key in os.environ}
    if name == "app-cli-forge":
        for key in ("SKELETON_GODOT_BIN", "GODOT_BINARY"):
            selected = os.environ.get(key)
            if selected:
                binary = Path(selected).resolve()
                if not binary.is_file() or not os.access(binary, os.X_OK):
                    rec.issue(suite=name, phase="preflight", kind="invalid-local-tool",
                              message="Selected Godot executable is unavailable", evidence="events.jsonl")
                    rec.suites.append({"id": name, "status": "failed", "duration_seconds": 0.0,
                                       "exit_code": 1, "timed_out": False})
                    return
                env[key] = str(binary)
                rec.emit("tool.bound", suite=name, variable=key,
                         binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    env["PYTHONUNBUFFERED"] = "1"
    started = time.monotonic()
    rec.emit("suite.started", suite=name, tier=suite["tier"],
             timeout_seconds=suite["timeout_seconds"],
             command_id=digest(json.dumps(suite["command"])))
    lines = 0
    discarded = 0
    timed_out = False
    code = None
    try:
        with logfile.open("w", encoding="utf-8") as sink:
            process = subprocess.Popen(
                cmd, cwd=ROOT / suite["cwd"], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, bufsize=0,
            )
            pending: queue.Queue = queue.Queue(maxsize=2048)

            def pump():
                try:
                    assert process.stdout is not None
                    while True:
                        chunk = process.stdout.readline(MAX_LINE)
                        if not chunk:
                            break
                        pending.put(chunk)
                finally:
                    pending.put(None)

            reader = threading.Thread(target=pump, daemon=True)
            reader.start()
            ended = False
            while not ended:
                if time.monotonic() - started > suite["timeout_seconds"] and not timed_out:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                try:
                    chunk = pending.get(timeout=0.2)
                except queue.Empty:
                    continue
                if chunk is None:
                    ended = True
                    continue
                if lines >= MAX_LINES:
                    discarded += 1
                    continue
                line = rec.redact(chunk.decode("utf-8", "replace").rstrip("\r\n"))
                # Bound per-line text and do not persist the original bytes.
                line = line[:MAX_LINE]
                sink.write(f"{timestamp()} [{name}] {line}\n")
                sink.flush()
                rec.emit("suite.output", suite=name, line=line)
                lines += 1
            code = process.wait(timeout=10)
            if discarded:
                sink.write(f"{timestamp()} [{name}] [TRUNCATED] {discarded} output chunks omitted\n")
        if private_xml is not None:
            junit_findings = parse_junit(private_xml, name, rec)
        else:
            junit_findings = 0
        if timed_out:
            rec.issue(suite=name, phase="execute", kind="timeout",
                      message=f"Suite exceeded {suite['timeout_seconds']}s; process group terminated",
                      evidence=f"logs/{name}.log")
        if code != 0 and not junit_findings:
            rec.issue(suite=name, phase="execute", kind="exit-nonzero",
                      message=f"Command exited with status {code}",
                      evidence=f"logs/{name}.log")
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        rec.issue(suite=name, phase="execute", kind="runner-error",
                  message=f"Runner failure type: {type(exc).__name__}",
                  evidence=f"logs/{name}.log")
    finally:
        if private_xml is not None:
            private_xml.unlink(missing_ok=True)
        elapsed = round(time.monotonic() - started, 3)
        status = "passed" if code == 0 and not timed_out and not any(
            item["suite"] == name and item["phase"] == "execute" for item in rec.issues
        ) else "failed"
        rec.suites.append({
            "id": name, "status": status, "duration_seconds": elapsed,
            "exit_code": code, "log": f"logs/{name}.log", "timed_out": timed_out,
            "logged_lines": lines, "truncated_lines": discarded,
            "tests": rec.test_counts.get(name),
        })
        rec.emit("suite.finished", suite=name, status=status,
                 elapsed_seconds=elapsed, exit_code=code, logged_lines=lines,
                 truncated_lines=discarded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "offline-e2e"), required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".e2e-evidence")
    parser.add_argument("--suite", action="append", default=[])
    args = parser.parse_args()
    try:
        redact = redactor()
    except Exception as exc:
        print(f"E2E evidence cannot safely log: {type(exc).__name__}", file=sys.stderr)
        return 2  # Never log without canonical redaction.
    rec = Recorder(args.output_dir.resolve(), redact)
    try:
        try:
            suites = load_manifest(args.manifest)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            rec.issue(suite="manifest", phase="preflight", kind="invalid-manifest",
                      message=f"Manifest failure type: {type(exc).__name__}",
                      evidence="machine/e2e_suites.json", severity="critical")
            rec.emit("preflight.failed", reason=type(exc).__name__)
            return 2
        selected = [s for s in suites if (s["id"] in args.suite if args.suite
                    else args.mode == "preflight" or s["tier"] == "offline")]
        unknown = set(args.suite) - {s["id"] for s in suites}
        if unknown:
            rec.issue(suite="manifest", phase="preflight", kind="unknown-suite",
                      message="Requested suite ID not registered", severity="critical")
            return 2
        if args.mode == "offline-e2e" and any(s["tier"] != "offline" for s in selected):
            rec.issue(suite="manifest", phase="preflight", kind="unsafe-suite",
                      message="Live-service suites are not permitted in offline-e2e mode",
                      severity="critical")
            return 2
        check_inventory(rec, selected)
        if rec.issues:
            return 1
        if args.mode == "offline-e2e":
            rec.suites.clear()
            for suite in selected:
                launch(rec, suite)
        return 1 if rec.issues else 0
    except Exception as exc:
        rec.issue(suite="harness", phase="execute", kind="unexpected-harness-error",
                  message=f"Unexpected failure type: {type(exc).__name__}", severity="critical")
        return 2
    finally:
        rec.finish(args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
