#!/usr/bin/env python3
"""Build/verify a bounded, ordered, non-padded Skeleton AI ecosystem archive.

The sole production output is an external, append-only tar artifact. This module
never places binaries/archives/weights in Git, fetches a model, signs a release,
or treats code presence as operational or security qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, BinaryIO

VERSION = 1
WAVES = tuple(f"MBW-{i:02}" for i in range(8))
CHUNK = 1024 * 1024
SHA256 = re.compile(r"^[0-9a-f]{64}$")
STAGE_ROOT = "bundle/stages"
MANIFEST_NAME = "bundle/manifest.json"
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
DIRECTORY = getattr(os, "O_DIRECTORY", 0)
CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class PackageError(RuntimeError):
    """A fail-closed content, provenance, ownership or size hold."""


def _canonical(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_relative(raw: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 700 or "\\" in raw or any(ord(c) < 32 for c in raw):
        raise PackageError(f"unsafe relative path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in raw.split("/")):
        raise PackageError(f"unsafe relative path: {raw!r}")
    if path.as_posix() != raw or raw.startswith("-"):
        raise PackageError(f"non-canonical relative path: {raw!r}")
    return raw


def _root_fd(path: Path) -> int:
    """Open root itself through a descriptor chain, rejecting symlinked parents."""
    if os.name != "posix" or not NOFOLLOW or not DIRECTORY:
        raise PackageError("secure package assembly requires POSIX O_NOFOLLOW/O_DIRECTORY")
    parts = path.absolute().parts
    fd = os.open("/", os.O_RDONLY | DIRECTORY | CLOEXEC)
    try:
        for part in parts[1:]:
            if part in ("", "."):
                continue
            if part == "..":
                raise PackageError("non-canonical root")
            next_fd = os.open(part, os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_beneath(root_fd: int, relative: str) -> BinaryIO:
    """Open regular file under a held directory chain; no symlink traversal."""
    parts = _safe_relative(relative).split("/")
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            new_fd = os.open(part, os.O_RDONLY | DIRECTORY | NOFOLLOW | CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = new_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | NOFOLLOW | CLOEXEC | getattr(os, "O_NONBLOCK", 0), dir_fd=fd)
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode):
                raise PackageError(f"not a regular file: {relative}")
            if info.st_size < 0:
                raise PackageError(f"invalid file size: {relative}")
            return os.fdopen(file_fd, "rb", buffering=0)
        except BaseException:
            os.close(file_fd)
            raise
    finally:
        os.close(fd)


def _load_json(fd: int, rel: str, *, max_size: int = 4 * 1024 * 1024) -> dict[str, Any]:
    with _open_beneath(fd, rel) as f:
        if os.fstat(f.fileno()).st_size > max_size:
            raise PackageError(f"JSON too large: {rel}")
        raw = f.read(max_size + 1)
    if len(raw) > max_size:
        raise PackageError(f"JSON too large: {rel}")
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise PackageError(f"duplicate JSON key in {rel}: {k}")
            out[k] = v
        return out
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError) as exc:
        raise PackageError(f"invalid JSON in {rel}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackageError(f"JSON object required: {rel}")
    return data


def _git(root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PackageError(f"git inspection unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise PackageError(f"git {' '.join(args)} failed: {proc.stderr[:250]!r}")
    return proc.stdout


def _tracked_ai(root: Path) -> list[str]:
    # Exact git index, not a recursive filesystem walk; untracked models excluded.
    raw = _git(root, "ls-files", "--stage", "-z", "--", "skeleton/ai")
    paths: list[str] = []
    for record in filter(None, raw.split(b"\0")):
        try:
            metadata, name = record.split(b"\t", 1)
            mode, _sha, stage = metadata.decode("ascii").split()
            path = name.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise PackageError("non-canonical Git index record") from exc
        if mode not in ("100644", "100755") or stage != "0":
            raise PackageError(f"symlink, submodule, or unmerged Git entry rejected: {path}")
        paths.append(_safe_relative(path))
    if not paths or len(paths) != len(set(paths)):
        raise PackageError("empty or duplicate canonical AI Git inventory")
    # HEAD may change independently: data in a dirty worktree is not source-bound.
    _git(root, "diff", "--quiet", "HEAD", "--", "skeleton/ai")
    return sorted(paths)


def _wave_contract(sequence: dict[str, Any]) -> list[dict[str, Any]]:
    if sequence.get("schema_version") != 1:
        raise PackageError("canonical sequence schema drift")
    waves = sequence.get("waves")
    if not isinstance(waves, list) or [w.get("id") for w in waves if isinstance(w, dict)] != list(WAVES):
        raise PackageError("canonical MBW-00..07 order drift")
    graph: dict[str, Any] = {}
    for index, wave in enumerate(waves):
        deps = wave.get("hard_dependencies")
        if not isinstance(deps, list) or len(deps) != len(set(deps)) or any(d not in WAVES[:index] for d in deps):
            raise PackageError(f"forward, duplicate or unknown build dependency: {wave.get('id')}")
        graph[wave["id"]] = deps
    return [{"id": w["id"], "dependencies": graph[w["id"]], "packages": w["work_packages"]} for w in waves]


def _profile(profile: dict[str, Any]) -> tuple[dict[str, list[str]], int, int, int]:
    if profile.get("schema_version") != VERSION or profile.get("source_root") != "skeleton/ai":
        raise PackageError("unsupported package profile")
    rules = profile.get("wave_prefixes")
    if not isinstance(rules, dict) or tuple(rules) != WAVES:
        raise PackageError("profile must bind all eight canonical waves in order")
    seen: set[str] = set()
    for wave, prefixes in rules.items():
        if not isinstance(prefixes, list) or not prefixes:
            raise PackageError(f"empty wave mapping: {wave}")
        for prefix in prefixes:
            _safe_relative(prefix)
            if not prefix.startswith("skeleton/ai/") or prefix in seen:
                raise PackageError(f"invalid or duplicate source prefix: {prefix}")
            seen.add(prefix)
    minimum, maximum = profile.get("minimum_archive_bytes"), profile.get("maximum_archive_bytes")
    minimum_payload = profile.get("minimum_source_bytes")
    if any(type(x) is not int or x <= 0 for x in (minimum, maximum, minimum_payload)):
        raise PackageError("invalid byte-size admission bounds")
    if minimum > maximum or minimum_payload > maximum:
        raise PackageError("inconsistent byte-size admission bounds")
    support = profile.get("support_files", {})
    if not isinstance(support, dict) or any(w not in WAVES for w in support):
        raise PackageError("invalid support_files wave assignments")
    for wave, names in support.items():
        if not isinstance(names, list):
            raise PackageError(f"invalid support paths for {wave}")
        for name in names:
            _safe_relative(name)
            if not (name in ("README.md", "pyproject.toml") or name.startswith(("machine/", "docs/", "scripts/"))):
                raise PackageError(f"support file not in approved metadata source tree: {name}")
    if len({n for paths in support.values() for n in paths}) != sum(len(p) for p in support.values()):
        raise PackageError("duplicate support file stage ownership")
    return rules, minimum, maximum, minimum_payload


def _stage_for(path: str, rules: dict[str, list[str]]) -> str:
    matches = [(len(prefix), wave) for wave, prefixes in rules.items() for prefix in prefixes
               if path == prefix or path.startswith(prefix + "/")]
    if not matches:
        raise PackageError(f"unclassified canonical AI path (mapping update required): {path}")
    matches.sort(reverse=True)
    if len(matches) > 1 and matches[0][0] == matches[1][0]:
        raise PackageError(f"ambiguous wave ownership: {path}")
    return matches[0][1]


class DigestReader:
    """Hash the exact bytes tar consumes, rejecting short reads and file mutation."""
    def __init__(self, src: BinaryIO, size: int):
        self.src, self.remaining = src, size
        self.digest = hashlib.sha256()
        self.consumed = 0

    def read(self, requested: int = -1) -> bytes:
        want = min(self.remaining, requested) if requested >= 0 else self.remaining
        if not want:
            return b""
        raw = self.src.read(want)
        if not raw:
            raise PackageError("source truncated during archive build")
        self.digest.update(raw)
        self.remaining -= len(raw)
        self.consumed += len(raw)
        return raw


def _record(tf: tarfile.TarFile, *, fd: int, source: str, destination: str, wave: str,
            expected_sha: str | None = None, expected_size: int | None = None,
            license_name: str = "repository", provenance: str = "git", kind: str = "source") -> dict[str, Any]:
    with _open_beneath(fd, source) as src:
        before = os.fstat(src.fileno())
        if before.st_size > 2_000_000_000:
            raise PackageError(f"individual source exceeds 2GB: {source}")
        if expected_size is not None and before.st_size != expected_size:
            raise PackageError(f"size mismatch: {source}")
        info = tarfile.TarInfo(destination)
        info.size, info.mtime, info.uid, info.gid, info.mode = before.st_size, 0, 0, 0, 0o644
        info.uname = info.gname = ""
        reader = DigestReader(src, before.st_size)
        tf.addfile(info, reader)
        after = os.fstat(src.fileno())
        if reader.remaining or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise PackageError(f"source mutation during build: {source}")
        sha = reader.digest.hexdigest()
        if expected_sha is not None and sha != expected_sha:
            raise PackageError(f"sha256 mismatch: {source}")
    return {"path": destination, "wave": wave, "size": before.st_size, "sha256": sha,
            "kind": kind, "license": license_name, "provenance": provenance}


def _artifact_items(fd: int, rel: str) -> list[dict[str, Any]]:
    data = _load_json(fd, rel)
    if data.get("schema_version") != VERSION or not isinstance(data.get("artifacts"), list):
        raise PackageError("artifact ledger schema invalid")
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for item in data["artifacts"]:
        if not isinstance(item, dict):
            raise PackageError("artifact record must be an object")
        file = _safe_relative(item.get("file"))
        dest = _safe_relative(item.get("destination"))
        wave = item.get("wave")
        if wave not in WAVES or dest in seen or not dest.startswith(("models/", "datasets/", "runtime/")):
            raise PackageError(f"artifact destination or wave invalid: {dest}")
        if dest.startswith("models/") and wave != "MBW-02":
            raise PackageError(f"model placement must be MBW-02: {dest}")
        sha, size = item.get("sha256"), item.get("bytes")
        if not isinstance(sha, str) or not SHA256.fullmatch(sha) or type(size) is not int or size <= 0:
            raise PackageError(f"artifact must have bounded bytes and sha256: {file}")
        if not isinstance(item.get("license"), str) or not item["license"].strip():
            raise PackageError(f"artifact has no license: {file}")
        if not isinstance(item.get("source"), str) or not item["source"].strip():
            raise PackageError(f"artifact has no provenance: {file}")
        if item.get("rights_approved") is not True:
            raise PackageError(f"artifact rights are not explicitly approved: {file}")
        seen.add(dest)
        records.append(item)
    if not any(x["destination"].startswith("models/") for x in records):
        raise PackageError("no approved, hash-pinned model: empty package is not AI-ready")
    return sorted(records, key=lambda x: (WAVES.index(x["wave"]), x["destination"]))


def _add_bytes(tf: tarfile.TarFile, name: str, raw: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.uid, info.gid, info.mode = len(raw), 0, 0, 0, 0o644
    info.uname = info.gname = ""
    tf.addfile(info, io.BytesIO(raw))


def _output_path(output: Path, repo: Path, payload: Path) -> Path:
    # Artifacts must not enter source Git or overwrite operator payloads.
    absolute = output.absolute()
    for restricted in (repo.absolute(), payload.absolute()):
        if absolute == restricted or restricted in absolute.parents:
            raise PackageError(f"output must be outside source and payload roots: {absolute}")
    if absolute.exists() or absolute.is_symlink():
        raise PackageError(f"output exists: {absolute}")
    if absolute.suffix != ".tar":
        raise PackageError("package filename must end with .tar")
    return absolute


def build(repo: Path, payload: Path, ledger: str, profile_path: str, output: Path) -> dict[str, Any]:
    output = _output_path(output, repo, payload)
    repo_fd = _root_fd(repo)
    payload_fd = _root_fd(payload)
    try:
        profile = _load_json(repo_fd, profile_path)
        rules, minimum, maximum, minimum_source = _profile(profile)
        waves = _wave_contract(_load_json(repo_fd, "machine/ai_master_build_sequence.json"))
        tracked = _tracked_ai(repo)
        support = profile.get("support_files", {})
        for extra_paths in support.values():
            tracked.extend(extra_paths)
        if len(tracked) != len(set(tracked)):
            raise PackageError("duplicate source path")
        _git(repo, "diff", "--quiet", "HEAD", "--", profile_path, "machine/ai_master_build_sequence.json", "scripts/build_ai_ecosystem_bundle.py", *[p for group in support.values() for p in group])
        tracked_files = set(_git(repo, "ls-files", "-z").decode("utf-8").split("\0"))
        if any(name not in tracked_files for group in support.values() for name in group):
            raise PackageError("missing Git-tracked support source file")
        indexed: dict[str, list[str]] = {wave: [] for wave in WAVES}
        support_owners = {path: wave for wave, names in support.items() for path in names}
        for path in tracked:
            indexed[support_owners.get(path) or _stage_for(path, rules)].append(path)
        for wave in indexed:
            indexed[wave].sort()
        if any(not group for group in indexed.values()):
            raise PackageError("every build wave must own at least one canonical source file")
        artifacts = _artifact_items(payload_fd, ledger)
        # Hold only one source file descriptor at a time during preflight.
        source_total = 0
        for path in tracked:
            with _open_beneath(repo_fd, path) as src:
                source_total += os.fstat(src.fileno()).st_size
        payload_total = sum(item["bytes"] for item in artifacts)
        if source_total + payload_total < minimum_source:
            raise PackageError(f"insufficient real bytes: {source_total + payload_total} < {minimum_source}")
        if source_total + payload_total > maximum:
            raise PackageError("declared input bytes exceed maximum archive bound")
        head = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", head):
            raise PackageError("invalid Git HEAD")
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_raw = tempfile.mkstemp(prefix=".skeleton-ai-bundle-", suffix=".partial", dir=output.parent)
        os.close(tmp_fd)
        tmp = Path(tmp_raw)
        try:
            records: list[dict[str, Any]] = []
            with tarfile.open(tmp, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for wave in WAVES:
                    for path in indexed[wave]:
                        records.append(_record(tar, fd=repo_fd, source=path,
                            destination=f"{STAGE_ROOT}/{wave}/source/{path}", wave=wave))
                    for item in artifacts:
                        if item["wave"] != wave:
                            continue
                        records.append(_record(tar, fd=payload_fd, source=item["file"],
                            destination=f"{STAGE_ROOT}/{wave}/payload/{item['destination']}", wave=wave,
                            expected_sha=item["sha256"], expected_size=item["bytes"],
                            license_name=item["license"], provenance=item["source"], kind="approved_artifact"))
                manifest = {"schema_version": VERSION, "package": "skeleton-ai-ecosystem",
                    "repository": "Apeloff1/Skeleton", "source_sha": head,
                    "sequence_sha256": hashlib.sha256(_canonical(_load_json(repo_fd, "machine/ai_master_build_sequence.json"))).hexdigest(),
                    "profile_sha256": hashlib.sha256(_canonical(profile)).hexdigest(),
                    "stage_graph": waves, "entries": records,
                    "source_bytes": source_total, "approved_artifact_bytes": payload_total,
                    "status": "content-only-no-release-attestation"}
                _add_bytes(tar, MANIFEST_NAME, _canonical(manifest))
            size = tmp.stat().st_size
            if not minimum <= size <= maximum:
                raise PackageError(f"real archive bytes outside 1.9GB admission window: {size} not in [{minimum}, {maximum}]")
            receipt = verify(tmp, minimum=minimum, maximum=maximum, required_source_bytes=minimum_source)
            with tmp.open("rb") as source:
                os.fsync(source.fileno())
            # Hardlink publication is no-clobber (os.replace would overwrite on race).
            os.link(tmp, output, follow_symlinks=False)
            parent_fd = os.open(output.parent, os.O_RDONLY | DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            receipt["archive"] = str(output)
            return receipt
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        os.close(payload_fd)
        os.close(repo_fd)


def verify(path: Path, *, minimum: int, maximum: int, required_source_bytes: int) -> dict[str, Any]:
    """Independent streaming verification: never extract an untrusted archive."""
    size = path.stat().st_size
    if not minimum <= size <= maximum:
        raise PackageError(f"archive size rejected: {size}")
    seen: set[str] = set()
    observed: list[dict[str, Any]] = []
    embedded: dict[str, Any] | None = None
    last_wave = -1
    with tarfile.open(path, mode="r|") as tf:
        for member in tf:
            name = _safe_relative(member.name)
            if name in seen or not member.isfile() or member.size < 0 or member.size > maximum:
                raise PackageError(f"unsafe or duplicate archive member: {name}")
            seen.add(name)
            if len(seen) > 200_000:
                raise PackageError("archive exceeds safe file count")
            src = tf.extractfile(member)
            if src is None:
                raise PackageError(f"member not readable: {name}")
            if name == MANIFEST_NAME:
                if embedded is not None or member.size > 40 * 1024 * 1024:
                    raise PackageError("duplicate or oversized manifest")
                raw = src.read(member.size + 1)
                if len(raw) != member.size:
                    raise PackageError("truncated manifest")
                try:
                    embedded = json.loads(raw)
                except ValueError as exc:
                    raise PackageError("invalid embedded manifest") from exc
                if _canonical(embedded) != raw:
                    raise PackageError("non-canonical embedded manifest")
                continue
            if embedded is not None:
                raise PackageError("manifest must be final archive entry")
            tokens = name.split("/")
            if len(tokens) < 5 or tokens[0:2] != ["bundle", "stages"] or tokens[2] not in WAVES or tokens[3] not in ("source", "payload"):
                raise PackageError(f"unrecognized archive member: {name}")
            rank = WAVES.index(tokens[2])
            if rank < last_wave:
                raise PackageError("build-wave archive order drift")
            last_wave = rank
            digest = hashlib.sha256()
            count = 0
            while True:
                data = src.read(CHUNK)
                if not data:
                    break
                count += len(data)
                if count > member.size:
                    raise PackageError("archive member overflow")
                digest.update(data)
            if count != member.size:
                raise PackageError("archive member truncated")
            observed.append({"path": name, "size": count, "sha256": digest.hexdigest(), "wave": tokens[2]})
    if embedded is None or embedded.get("schema_version") != VERSION or embedded.get("status") != "content-only-no-release-attestation":
        raise PackageError("manifest or release hold missing")
    records = embedded.get("entries")
    if not isinstance(records, list) or len(records) != len(observed):
        raise PackageError("manifest inventory mismatch")
    for a, b in zip(observed, records):
        if not isinstance(b, dict) or any(b.get(k) != value for k, value in a.items()):
            raise PackageError(f"sha256, size, order or stage mismatch: {a['path']}")
    graph = embedded.get("stage_graph")
    if not isinstance(graph, list) or [w.get("id") for w in graph if isinstance(w, dict)] != list(WAVES):
        raise PackageError("missing canonical stage graph")
    for idx, wave in enumerate(graph):
        deps = wave.get("dependencies")
        if not isinstance(deps, list) or any(d not in WAVES[:idx] for d in deps):
            raise PackageError("invalid dependency graph")
    source_bytes = sum(r["size"] for r in records if r.get("kind") == "source")
    artifact_bytes = sum(r["size"] for r in records if r.get("kind") == "approved_artifact")
    if embedded.get("source_bytes") != source_bytes or embedded.get("approved_artifact_bytes") != artifact_bytes:
        raise PackageError("embedded byte accounting disagrees")
    if source_bytes + artifact_bytes < required_source_bytes:
        raise PackageError("insufficient actual content bytes")
    if not any(r.get("kind") == "approved_artifact" and "/payload/models/" in r["path"] for r in records):
        raise PackageError("missing content-addressed model artifact")
    return {"status": "integrity-verified-not-release-certified", "archive_bytes": size,
            "source_bytes": source_bytes, "approved_artifact_bytes": artifact_bytes,
            "entries": len(records), "sha256_manifest": hashlib.sha256(_canonical(embedded)).hexdigest(),
            "source_sha": embedded.get("source_sha"), "waves": list(WAVES)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo-root", type=Path, default=Path("."))
    b.add_argument("--payload-root", type=Path, required=True)
    b.add_argument("--artifact-ledger", default="approved_artifacts.json", help="relative to payload root")
    b.add_argument("--profile", default="machine/ai_ecosystem_bundle_v1.json")
    b.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("archive", type=Path)
    v.add_argument("--minimum-archive-bytes", type=int, default=1_880_000_000)
    v.add_argument("--maximum-archive-bytes", type=int, default=1_920_000_000)
    v.add_argument("--minimum-source-bytes", type=int, default=1_850_000_000)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.repo_root, args.payload_root, args.artifact_ledger, args.profile, args.output)
        else:
            result = verify(args.archive, minimum=args.minimum_archive_bytes,
                            maximum=args.maximum_archive_bytes, required_source_bytes=args.minimum_source_bytes)
    except (PackageError, OSError, tarfile.TarError) as exc:
        print(f"AI ecosystem package: HOLD: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
