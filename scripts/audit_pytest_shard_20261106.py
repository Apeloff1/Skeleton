#!/usr/bin/env python3
"""Run one deterministic shard of ALL tracked pytest test_*.py modules in a scope."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def bounded_log_tail(path: Path, *, max_bytes: int = 131072, max_lines: int = 180) -> str:
    """Emit only a bounded tail; never materialize an unbounded pytest log."""
    if type(max_bytes) is not int or not 0 < max_bytes <= 1048576:
        raise ValueError("invalid log byte bound")
    if type(max_lines) is not int or not 0 < max_lines <= 500:
        raise ValueError("invalid log line bound")
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - max_bytes))
        data = stream.read(max_bytes)
    if size > max_bytes:
        # Discard a partial first line; do not fabricate an entire failing log.
        boundary = data.find(b"\n")
        data = data[boundary + 1:] if boundary >= 0 else b""
    return "\n".join(data.decode("utf-8", errors="replace").splitlines()[-max_lines:])


def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: audit_pytest_shard_20261106.py AREA SHARD TOTAL_SHARDS")
        return 2
    area, shard_str, total_str = sys.argv[1:]
    shard = int(shard_str)
    total = int(total_str)
    if total < 1 or not 0 <= shard < total:
        raise ValueError("invalid shard index")
    if area not in ("skeleton/testing", "tests", "backend/tests", "uncovered"):
        raise ValueError("unknown test scope")

    files = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    all_tests = sorted(os.fsdecode(item) for item in files if item and
                       os.path.basename(os.fsdecode(item)).startswith("test_") and
                       os.fsdecode(item).endswith(".py"))
    if area == "uncovered":
        covered = ("skeleton/testing", "tests", "backend/tests")
        tests = [p for p in all_tests if not any(p.startswith(base + "/") for base in covered)]
    else:
        tests = [p for p in all_tests if p.startswith(area + "/")]
    selected = [p for p in tests if int.from_bytes(
        hashlib.sha256(p.encode("utf-8")).digest()[:8], "big"
    ) % total == shard]
    result_dir = Path("audit-sweep-results")
    result_dir.mkdir(exist_ok=True)
    key = area.replace("/", "-") + f"-{shard}-of-{total}"
    metadata = {
        "area": area, "shard": shard, "total_shards": total,
        "all_test_modules": len(tests), "selected_modules": len(selected),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "paths": selected,
    }
    (result_dir / f"{key}-selection.json").write_text(json.dumps(metadata, indent=2))
    if not selected:
        print("ERROR: shard has no test modules")
        return 2

    log = result_dir / f"{key}-pytest.log"
    xml = result_dir / f"{key}-pytest.xml"
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-ra",
           f"--junitxml={xml}", *selected]
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as handle:
        try:
            proc = subprocess.run(
                cmd, text=True, stdout=handle, stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONPATH": ".:backend"},
                timeout=4500,
                check=False,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 124
            handle.write("\nERROR: pytest shard timed out after 4500 seconds\n")
    metadata["duration_seconds"] = round(time.monotonic() - started, 2)
    metadata["exit_code"] = code
    (result_dir / f"{key}-selection.json").write_text(json.dumps(metadata, indent=2))
    print(f"Scope={area}, shard={shard}/{total}, modules={len(selected)}, exit={code}")
    print(bounded_log_tail(log))
    return code


if __name__ == "__main__":
    sys.exit(main())
