#!/usr/bin/env python3
"""Compare two *live* Git checkouts byte-for-byte without contacting a VM.

Run on a trusted host that can read both the Codex checkout and the VM
checkout. A GitHub PR being merged does not prove a deployed VM matches it.
Both checkouts must be clean, at an operator-supplied exact commit, and have
matching tracked file bytes, symlink targets, and executable bits.

Ignored files, deployment secrets, live databases, model weights outside the
checkout, Docker image digests, and running-process state are NOT certified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

MAX_FINDINGS = 40


class ParityError(RuntimeError):
    """Evidence is missing or invalid; never convert this into success."""


def git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=60,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ParityError("Git inspection unavailable") from exc
    if result.returncode:
        raise ParityError("Git inspection failed: " + " ".join(args))
    return result.stdout


def inspect(root: Path, required_sha: str) -> dict[str, tuple[str, str]]:
    if not root.is_dir():
        raise ParityError("checkout directory unavailable")
    try:
        top = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel").strip())).resolve()
    except (OSError, ValueError) as exc:
        raise ParityError("checkout root cannot be verified") from exc
    if top != root.resolve():
        raise ParityError("path is not the root of its Git checkout")
    if git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip() != required_sha:
        raise ParityError("checkout HEAD does not match required GitHub main SHA")
    if git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise ParityError("checkout has staged, modified, deleted or untracked files")
    tree = git(root, "ls-tree", "-r", "-z", "HEAD")
    entries: dict[str, tuple[str, str]] = {}
    for record in tree.split(b"\0"):
        if not record:
            continue
        try:
            header, path_bytes = record.split(b"\t", 1)
            mode, kind, oid = header.split(b" ", 2)
            relative = path_bytes.decode("utf-8", "strict")
        except (ValueError, UnicodeError) as exc:
            raise ParityError("Git tree contains an unreadable path") from exc
        if kind != b"blob" or mode not in (b"100644", b"100755", b"120000"):
            raise ParityError("checkout contains a submodule or unsupported tracked entry")
        if relative in entries or relative.startswith("/") or any(
            part in ("", ".", "..") for part in relative.split("/")
        ):
            raise ParityError("Git tree path is not safe and canonical")
        name = root / relative
        try:
            # A tracked regular file may not be reached through an untracked
            # symlinked parent. Git skip-worktree can conceal that substitution
            # from porcelain status, even if the target bytes still hash to
            # the committed Git object.
            ancestor = root
            for component in relative.split("/")[:-1]:
                ancestor = ancestor / component
                if not stat.S_ISDIR(ancestor.lstat().st_mode):
                    raise ParityError("tracked checkout ancestor is not a real directory: " + relative)
            info = name.lstat()
            if mode == b"120000":
                if not stat.S_ISLNK(info.st_mode):
                    raise ParityError("tracked symbolic link not present as a symbolic link")
                raw = os.fsencode(os.readlink(name))
                git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
            else:
                if not stat.S_ISREG(info.st_mode):
                    raise ParityError("tracked regular file missing or replaced")
                if bool(info.st_mode & stat.S_IXUSR) != (mode == b"100755"):
                    raise ParityError("tracked executable mode differs from Git")
                digest = hashlib.sha256()
                # Match the original Git blob as well as the other checkout.
                # A suppressed dirty status or identically modified checkouts
                # must not forge a positive GitHub main attestation.
                # LFS smudge replacements need separate custody evidence.
                git_blob_digest = hashlib.sha1()
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                with os.fdopen(os.open(name, flags), "rb") as stream:
                    info_open = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info_open.st_mode):
                        raise ParityError("tracked file changed type during read")
                    git_blob_digest.update(b"blob " + str(info_open.st_size).encode("ascii") + b"\0")
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                        git_blob_digest.update(chunk)
                git_blob = git_blob_digest.hexdigest()
                raw = None
            if git_blob != oid.decode("ascii"):
                raise ParityError("tracked checkout bytes differ from Git blob: " + relative)
        except (OSError, UnicodeError) as exc:
            raise ParityError("tracked checkout file cannot be read: " + relative) from exc
        entries[relative] = (
            mode.decode("ascii"),
            hashlib.sha256(raw).hexdigest() if raw is not None else digest.hexdigest(),
        )
    return entries


def compare(codex: Path, vm: Path, required_sha: str) -> dict[str, object]:
    if len(required_sha) != 40 or any(ch not in "0123456789abcdef" for ch in required_sha):
        raise ParityError("required commit must be a full lowercase SHA-1")
    if codex.resolve() == vm.resolve():
        raise ParityError("Codex and VM roots must be distinct checkouts")
    left = inspect(codex, required_sha)
    right = inspect(vm, required_sha)
    keys = sorted(left.keys() | right.keys())
    different = [name for name in keys if left.get(name) != right.get(name)]
    if different:
        raise ParityError(
            f"tracked checkout mismatch in {len(different)} paths: "
            + ", ".join(different[:MAX_FINDINGS])
        )
    encoded = json.dumps(
        [(path, *left[path]) for path in keys], ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema": "skeleton.codex-vm-source-parity.v1",
        "verdict": "identical_tracked_source",
        "required_commit": required_sha,
        "tracked_files": len(keys),
        "source_receipt_sha256": hashlib.sha256(encoded).hexdigest(),
        "excluded": [
            "ignored_files_and_secrets", "databases_and_external_weights",
            "built_artifacts_and_container_images", "running_vm_process_state",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-root", type=Path, required=True)
    parser.add_argument("--vm-root", type=Path, required=True)
    parser.add_argument("--required-sha", required=True)
    args = parser.parse_args(argv)
    try:
        report = compare(args.codex_root, args.vm_root, args.required_sha)
    except ParityError as exc:
        print(json.dumps({"schema": "skeleton.codex-vm-source-parity.v1",
                          "verdict": "not_verified", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
