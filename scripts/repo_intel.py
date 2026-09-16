#!/usr/bin/env python3
"""Fast repository intelligence, build mapping, gap detection, and agent gates.

The scanner intentionally uses Git's index as its primary database. Clean files do
not need to be opened or re-hashed; only unstaged files are hashed from the working
tree. This keeps the command useful in a large monorepo and cheap enough to run at
the start/end of every agent session and in CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "repo-intel"
DEFAULT_OUT = ROOT / ".cache" / "repo-intel"
GENERATED_NAMES = {
    "index.json",
    "build-map.json",
    "gaps.json",
    "security-quality.json",
    "notes.md",
    "dependabot-notes.md",
}


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if check and proc.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def load_json(name: str) -> Any:
    path = CONFIG_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing repo-intel config: {path}") from exc


def indexed_files() -> list[dict[str, Any]]:
    """Return tracked paths and Git index blobs, hashing only unstaged paths."""
    raw = git("ls-files", "-s", "-z")
    rows: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    for record in raw.split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode, blob, stage = meta.split()
        if stage != "0":
            continue
        row = {"path": path, "mode": mode, "blob": blob}
        rows.append(row)
        by_path[path] = row

    dirty = set(filter(None, git("diff", "--name-only", "-z").split("\0")))
    existing_dirty = [p for p in sorted(dirty) if p in by_path and (ROOT / p).is_file()]
    if existing_dirty:
        proc = subprocess.run(
            ["git", "hash-object", "--stdin-paths"], cwd=ROOT, text=True,
            input="\n".join(existing_dirty) + "\n", stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
        if proc.returncode == 0:
            hashes = proc.stdout.splitlines()
            if len(hashes) == len(existing_dirty):
                for path, blob in zip(existing_dirty, hashes):
                    by_path[path]["blob"] = blob
                    by_path[path]["working_tree"] = True

    for row in rows:
        path = ROOT / row["path"]
        try:
            row["size"] = path.stat().st_size
        except OSError:
            row["size"] = 0
        row.setdefault("working_tree", False)
    return sorted(rows, key=lambda item: item["path"])


def classify(path: str, config: dict[str, Any]) -> str:
    candidates = []
    for subsystem in config["subsystems"]:
        root = subsystem["root"].rstrip("/")
        if path == root or path.startswith(root + "/"):
            candidates.append((len(root), subsystem["id"]))
    return max(candidates, default=(0, "root"))[1]


def role_for(path: str) -> str:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if path.startswith(".github/workflows/"):
        return "ci-workflow"
    if name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
        return "container-build"
    if name in {"pyproject.toml", "package.json", "package-lock.json", "requirements.txt", "requirements-dev.txt"}:
        return "dependency-manifest"
    if suffix in {".md", ".rst"}:
        return "documentation"
    if suffix in {".py", ".pyi"}:
        return "python-source"
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        return "js-source"
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        return "configuration"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".mp3", ".wav", ".ogg"}:
        return "asset"
    if suffix in {".so", ".dll", ".dylib", ".exe", ".bin", ".a", ".apk", ".aab"} or suffix == "":
        return "binary-or-executable"
    return "other"


def digest_rows(rows: Iterable[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for row in rows:
        path = row["path"]
        if path.startswith(".cache/"):
            continue
        h.update(path.encode())
        h.update(b"\0")
        h.update(str(row["blob"]).encode())
        h.update(b"\n")
    return h.hexdigest()


def build_snapshot() -> dict[str, Any]:
    config = load_json("config.json")
    rows = indexed_files()
    for row in rows:
        row["subsystem"] = classify(row["path"], config)
        row["role"] = role_for(row["path"])

    subsystem_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        subsystem_rows.setdefault(row["subsystem"], []).append(row)

    subsystems = []
    for item in config["subsystems"]:
        members = subsystem_rows.get(item["id"], [])
        roles: dict[str, int] = {}
        for member in members:
            roles[member["role"]] = roles.get(member["role"], 0) + 1
        subsystems.append({
            **item,
            "file_count": len(members),
            "bytes": sum(int(m["size"]) for m in members),
            "roles": dict(sorted(roles.items())),
            "present": bool(members),
        })

    large = [
        {"path": r["path"], "bytes": r["size"], "subsystem": r["subsystem"]}
        for r in rows if int(r["size"]) >= int(config["thresholds"]["large_tracked_bytes"])
    ]
    large.sort(key=lambda x: x["bytes"], reverse=True)

    return {
        "schema": 2,
        "source_digest": digest_rows(rows),
        "tracked_files": len(rows),
        "tracked_bytes": sum(int(r["size"]) for r in rows),
        "subsystems": subsystems,
        "large_tracked_files": large,
        "files": rows,
    }


def feature_gaps(snapshot: dict[str, Any]) -> dict[str, Any]:
    config = load_json("game-capabilities.json")
    paths = [row["path"].lower() for row in snapshot["files"]]
    results = []
    for capability in config["capabilities"]:
        anchors = [a.lower() for a in capability.get("anchors", [])]
        evidence = sorted({p for p in paths if any(anchor in p for anchor in anchors)})
        min_evidence = int(capability.get("min_evidence", 1))
        if len(evidence) >= min_evidence:
            status = "present-surface"
        elif evidence:
            status = "partial-surface"
        else:
            status = "missing-surface"
        results.append({**capability, "status": status, "evidence": evidence[:20]})
    counts: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "schema": 2,
        "target": config["target"],
        "status_semantics": "Surface evidence is structural only; it is not proof of production readiness.",
        "counts": counts,
        "capabilities": results,
    }


def security_quality(snapshot: dict[str, Any]) -> dict[str, Any]:
    paths = {row["path"] for row in snapshot["files"]}
    dependabot_text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8") if (ROOT / ".github" / "dependabot.yml").exists() else ""
    expected = {
        "dependabot": ".github/dependabot.yml",
        "codeql": ".github/workflows/codeql.yml",
        "dependency_review": ".github/workflows/dependency-review.yml",
        "dependency_security": ".github/workflows/dependency-security.yml",
        "secret_scanning": ".github/workflows/secret-scanning.yml",
        "gitleaks_config": ".gitleaks.toml",
    }
    controls = {name: path in paths for name, path in expected.items()}
    ecosystems = [name for name in ["github-actions", "pip", "npm", "docker"] if f"package-ecosystem: {name}" in dependabot_text]
    findings = []
    for item in snapshot["large_tracked_files"]:
        findings.append({
            "severity": "medium",
            "kind": "repository-performance",
            "path": item["path"],
            "note": "Large tracked artifact increases clone, checkout, cache, and agent workspace cost; justify, LFS, release-asset, or fetch-on-demand it.",
        })
    if not all(controls.values()):
        findings.append({
            "severity": "medium",
            "kind": "security-control-coverage",
            "missing": sorted(name for name, present in controls.items() if not present),
            "note": "Expected repository security controls are absent from the tracked tree.",
        })
    return {
        "schema": 2,
        "controls": controls,
        "dependabot_ecosystems": ecosystems,
        "dependabot_live_alerts": "collected separately by CI when repository permissions allow",
        "findings": findings,
    }


def build_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    cfg = load_json("config.json")
    return {
        "schema": 2,
        "source_digest": snapshot["source_digest"],
        "entrypoints": cfg["entrypoints"],
        "subsystems": snapshot["subsystems"],
        "agent_protocol": cfg["agent_protocol"],
        "hot_paths": [s["id"] for s in snapshot["subsystems"] if s["file_count"] >= cfg["thresholds"]["hot_subsystem_files"]],
    }


def render_notes(snapshot: dict[str, Any], gaps: dict[str, Any], sq: dict[str, Any]) -> str:
    missing = [c for c in gaps["capabilities"] if c["status"] != "present-surface"]
    missing.sort(key=lambda c: (c.get("priority", 99), c["id"]))
    large = snapshot["large_tracked_files"]
    lines = [
        "# Repository intelligence notes",
        "",
        f"Source digest: `{snapshot['source_digest']}`",
        f"Tracked surface: **{snapshot['tracked_files']} files** / **{snapshot['tracked_bytes']:,} bytes**.",
        "",
        "## Noticeable gaps ready for build augmentation",
        "",
    ]
    if missing:
        for item in missing[:30]:
            lines.append(f"- **P{item.get('priority', '?')} · {item['name']}** — {item['status']}. {item.get('build_note', '')}".rstrip())
    else:
        lines.append("- No structural capability gaps detected. Functional/eval readiness still requires evidence.")
    lines.extend(["", "## Security and quality notes", ""])
    lines.append("- Dependabot ecosystems configured: " + (", ".join(sq["dependabot_ecosystems"]) or "none detected") + ".")
    if large:
        for item in large[:10]:
            mib = item["bytes"] / (1024 * 1024)
            lines.append(f"- Large tracked artifact: `{item['path']}` ({mib:.1f} MiB). Treat as a build-speed and supply-chain review point.")
    for finding in sq["findings"]:
        if finding["kind"] != "repository-performance":
            lines.append(f"- {finding['kind']}: {finding['note']}")
    lines.extend([
        "",
        "## Agent/build handoff contract",
        "",
        "- Read this snapshot before changing build-affecting code.",
        "- Claim one or more IDs from `repo-intel/batches.json`; avoid overlapping ownership unless explicitly coordinated.",
        "- Add a note under `repo-intel/notes/` describing changed capability, validation, security/quality effect, and remaining gap.",
        "- Run `make repo-intel` and `make repo-intel-check` before handoff.",
        "- Treat `present-surface` as discoverability evidence, not proof that the feature is complete or competitive.",
        "",
    ])
    return "\n".join(lines)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def snapshot_command(out: Path) -> None:
    snapshot = build_snapshot()
    gaps = feature_gaps(snapshot)
    sq = security_quality(snapshot)
    mapping = build_map(snapshot)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "index.json", snapshot)
    write_json(out / "build-map.json", mapping)
    write_json(out / "gaps.json", gaps)
    write_json(out / "security-quality.json", sq)
    (out / "notes.md").write_text(render_notes(snapshot, gaps, sq), encoding="utf-8")
    print(f"repo-intel: wrote snapshot to {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


def changed_paths(base: str) -> list[str]:
    output = git("diff", "--name-only", f"{base}...HEAD", check=False)
    if not output.strip():
        output = git("diff", "--name-only", "HEAD~1...HEAD", check=False)
    return sorted(filter(None, output.splitlines()))


def note_gate(base: str) -> None:
    cfg = load_json("config.json")
    changed = changed_paths(base)
    if not changed:
        print("repo-intel: no changed paths to gate")
        return
    impact = [
        p for p in changed
        if any(p == prefix.rstrip("/") or p.startswith(prefix) for prefix in cfg["build_affecting_prefixes"])
        and not p.startswith("repo-intel/notes/")
    ]
    notes = [p for p in changed if p.startswith("repo-intel/notes/") and p.endswith(".md")]
    if impact and not notes:
        preview = "\n  - ".join(impact[:20])
        raise RuntimeError(
            "build-affecting changes require an augmentation note under repo-intel/notes/.\n"
            f"Changed build surface:\n  - {preview}\n"
            "Copy repo-intel/notes/TEMPLATE.md, record batch IDs, validation, security/quality impact, and remaining gaps."
        )
    print(f"repo-intel: note gate passed ({len(impact)} build paths, {len(notes)} notes)")


def validate_configs() -> None:
    cfg = load_json("config.json")
    caps = load_json("game-capabilities.json")
    batches = load_json("batches.json")
    ids = [b["id"] for b in batches["batches"]]
    if batches.get("batch_count") != 100 or len(ids) != 100 or len(set(ids)) != 100:
        raise RuntimeError("repo-intel/batches.json must define exactly 100 unique batches")
    cap_ids = [c["id"] for c in caps["capabilities"]]
    if len(cap_ids) != len(set(cap_ids)):
        raise RuntimeError("game capability IDs must be unique")
    subsystem_ids = [s["id"] for s in cfg["subsystems"]]
    if len(subsystem_ids) != len(set(subsystem_ids)):
        raise RuntimeError("subsystem IDs must be unique")
    required = {"security", "quality", "gameplay", "build", "ai"}
    lanes = {b["lane"] for b in batches["batches"]}
    if not required.issubset(lanes):
        raise RuntimeError(f"100-batch plan must include lanes: {sorted(required)}")
    print(f"repo-intel: config valid ({len(subsystem_ids)} subsystems, {len(cap_ids)} game capabilities, {len(ids)} batches)")


def dependabot_notes(alerts_path: Path | None, prs_path: Path | None, out: Path) -> None:
    lines = ["# Dependabot security and quality notes", ""]
    def read_payload(path: Path | None) -> Any:
        if not path or not path.exists() or path.stat().st_size == 0:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    alerts = read_payload(alerts_path)
    prs = read_payload(prs_path)
    if isinstance(alerts, list):
        open_alerts = [a for a in alerts if a.get("state", "open") == "open"]
        lines.append(f"- Open Dependabot alerts visible to this workflow: **{len(open_alerts)}**.")
        severity: dict[str, int] = {}
        for alert in open_alerts:
            sev = (((alert.get("security_advisory") or {}).get("severity")) or "unknown").lower()
            severity[sev] = severity.get(sev, 0) + 1
        if severity:
            lines.append("- Alert severity mix: " + ", ".join(f"{k}={v}" for k, v in sorted(severity.items())) + ".")
    else:
        lines.append("- Live Dependabot alert API was unavailable to this workflow token; static Dependabot coverage is still indexed.")
    if isinstance(prs, dict):
        items = prs.get("items", [])
        lines.append(f"- Open Dependabot PRs: **{len(items)}**.")
        for item in items[:20]:
            lines.append(f"  - #{item.get('number')}: {item.get('title', 'untitled')}")
    else:
        lines.append("- Open Dependabot PR data unavailable.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"repo-intel: wrote {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot", help="generate fast machine + human repo intelligence")
    snap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub.add_parser("check", help="validate repo-intel configuration contracts")
    gate = sub.add_parser("gate", help="require augmentation notes for build-affecting changes")
    gate.add_argument("--base", default=os.environ.get("REPO_INTEL_BASE", "origin/main"))
    dep = sub.add_parser("dependabot-notes", help="render live Dependabot/API data as build notes")
    dep.add_argument("--alerts", type=Path)
    dep.add_argument("--prs", type=Path)
    dep.add_argument("--out", type=Path, default=DEFAULT_OUT / "dependabot-notes.md")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            snapshot_command(args.out)
        elif args.command == "check":
            validate_configs()
        elif args.command == "gate":
            validate_configs()
            note_gate(args.base)
        elif args.command == "dependabot-notes":
            dependabot_notes(args.alerts, args.prs, args.out)
        return 0
    except RuntimeError as exc:
        print(f"repo-intel: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
