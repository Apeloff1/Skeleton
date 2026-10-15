#!/usr/bin/env python3
"""Read-only, Git-object-based audit of archived satellite checkout integrity.

Works without checking out problematic case-colliding paths on Windows.
Findings for stubs and truncation are review candidates, not automatic deletions.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".md", ".toml")
MAX_SCAN_BYTES = 262144
STALE_UI = re.compile(r"(?:(?:components/|@/components/)UI/|(?:\.\.?/)UI/)")
STUB = re.compile(
    r"\b(?:TODO|FIXME|NotImplementedError)\b|"
    r"throw\s+new\s+Error\s*\(\s*['\\"](?:not implemented|TODO)",
    re.I,
)
TRUNC = re.compile(r"\[truncated\]|<truncated>|content truncated|output truncated", re.I)
WINDOWS_CHARS = re.compile(r'[<>:"\\|?*\x00-\x1f\x7f-\x9f]')
DEVICE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$",
    re.I,
)

def run_git(*args: str) -> bytes:
    return subprocess.run(["git", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout

def paths_at(ref: str) -> list[tuple[str, str, int]]:
    records = run_git("ls-tree", "-r", "-l", "-z", ref, "--", "satellites/").split(b"\0")
    result = []
    for rec in records:
        if not rec:
            continue
        header, path = rec.split(b"\t", 1)
        fields = header.decode("ascii").split()
        if len(fields) != 4 or fields[1] != "blob":
            continue
        size = int(fields[3]) if fields[3] != "-" else -1
        result.append((path.decode("utf-8", "surrogateescape"), fields[2], size))
    return result

def path_problem(path: str) -> list[str]:
    parts = path.split("/")
    problems = []
    try:
        byte_length = len(path.encode("utf-8"))
        utf16_length = len(path.encode("utf-16-le")) // 2
    except UnicodeEncodeError:
        return ["invalid UTF-8"]
    if max(byte_length, utf16_length) > 190:
        problems.append("path exceeds 190 units")
    for part in parts:
        if max(len(part.encode("utf-8")), len(part.encode("utf-16-le")) // 2) > 180:
            problems.append("component exceeds 180 units")
        if (WINDOWS_CHARS.search(part) or DEVICE.fullmatch(part)
                or part.endswith((" ", ".")) or part.casefold() == ".git"
                or any(0x202A <= ord(ch) <= 0x202E or 0x2066 <= ord(ch) <= 0x2069 for ch in part)):
            problems.append("Windows-invalid component")
    return sorted(set(problems))

def normalized(part: str) -> str:
    return unicodedata.normalize("NFC", part.casefold())

def content_audit(records: list[tuple[str, str, int]], max_bytes: int, max_examples: int) -> tuple[dict, list]:
    candidates = [(path, sha) for path, sha, size in records
                  if path.endswith(SOURCE_SUFFIXES) and 0 <= size <= max_bytes]
    findings = []
    counts = Counter()
    content_cache: dict[str, bytes] = {}
    proc = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        for path, sha in candidates:
            if sha not in content_cache:
                proc.stdin.write((sha + "\n").encode("ascii"))
                proc.stdin.flush()
                header = proc.stdout.readline().decode("ascii", "replace").strip().split()
                if len(header) != 3 or header[0] != sha or header[1] != "blob":
                    raise ValueError(f"unexpected Git object header: {header}")
                length = int(header[2])
                content_cache[sha] = proc.stdout.read(length)
                if proc.stdout.read(1) != b"\n":
                    raise ValueError("missing Git object separator")
            raw = content_cache[sha]
            if b"\0" in raw:
                continue
            txt = raw.decode("utf-8", "replace")
            is_frontend = "/frontend/" in path and path.endswith((".ts", ".tsx", ".js", ".jsx"))
            for kind, match in (
                ("stale_ui_reference", STALE_UI.search(txt) if is_frontend else None),
                ("stub_marker", STUB.search(txt) if path.endswith((".ts", ".tsx", ".js", ".jsx", ".py")) else None),
                ("truncation_marker", TRUNC.search(txt)),
            ):
                if match:
                    counts[kind] += 1
                    if len(findings) < max_examples:
                        line = txt.count("\n", 0, match.start()) + 1
                        findings.append({"kind": kind, "path": path, "line": line,
                                         "sample": txt.splitlines()[line - 1].strip()[:160]})
            if path.endswith(".json"):
                try:
                    json.loads(txt)
                except (ValueError, UnicodeDecodeError) as exc:
                    counts["invalid_json"] += 1
                    if len(findings) < max_examples:
                        findings.append({"kind": "invalid_json", "path": path, "sample": str(exc)[:160]})
    finally:
        proc.stdin.close()
        proc.stdout.close()
        proc.wait()
    return dict(counts), findings

def audit(ref: str, max_bytes: int = MAX_SCAN_BYTES, max_examples: int = 100) -> dict:
    files = paths_at(ref)
    names: dict[tuple[str, ...], tuple[str, str]] = {}
    collision_keys: set[tuple[str, ...]] = set()
    path_issues = []
    for path, _sha, _size in files:
        reasons = path_problem(path)
        if reasons:
            path_issues.append({"path": path, "reasons": reasons})
        parts = path.split("/")
        for i in range(1, len(parts) + 1):
            key = tuple(map(normalized, parts[:i]))
            entry = ("/".join(parts[:i]), "file" if i == len(parts) else "directory")
            if key in names and names[key] != entry:
                collision_keys.add(key)
            else:
                names[key] = entry
    counts, examples = content_audit(files, max_bytes, max_examples)
    return {
        "revision": ref,
        "tracked_files": len(files),
        "path_issues": path_issues[:max_examples],
        "path_issue_count": len(path_issues),
        "collision_count": len(collision_keys),
        "collisions": ["/".join(key) for key in sorted(collision_keys)[:max_examples]],
        "content_counts": counts,
        "examples": examples,
        "scan_byte_limit_per_file": max_bytes,
        "notes": "Stub and truncation markers are candidates, not proof of incomplete implementation; oversized files are omitted from content inspection.",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--max-bytes", type=int, default=MAX_SCAN_BYTES)
    parser.add_argument("--max-examples", type=int, default=100)
    parser.add_argument("--fail-on-ui-refs", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(args.ref, args.max_bytes, args.max_examples)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"satellite-audit: failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["collision_count"] or report["path_issue_count"]:
        return 1
    if args.fail_on_ui_refs and report["content_counts"].get("stale_ui_reference", 0):
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
