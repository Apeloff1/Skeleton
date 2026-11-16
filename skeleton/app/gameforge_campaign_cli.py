"""Installed offline campaign commands and explicit local revision workspace."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import stat
import sys
from typing import BinaryIO, Iterator, Sequence, TextIO

from skeleton.app.gameforge_campaign import (
    append_actions, build_campaign, play_campaign, verify_campaign, verify_session,
)
from skeleton.app.gameforge_campaign_store import CampaignStore, CampaignStoreError
from skeleton.app.original_quest_cli import _encode, _object, _require, read_document
from skeleton.gameforge.errors import GameForgeError


def _private_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CampaignStoreError("workspace file is not private regular storage")
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise CampaignStoreError("workspace file has unsafe ownership or permissions")
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise CampaignStoreError("workspace file is a reparse point")


@contextmanager
def open_workspace(path: Path, *, create: bool) -> Iterator[CampaignStore]:
    """Trusted operator-specified local directory; no JSON-derived path or URI."""
    target = path.expanduser().absolute()
    parent = target.parent
    if parent.resolve(strict=True) != parent or not parent.is_dir():
        raise CampaignStoreError("workspace parent must be a real local directory")
    info = parent.stat()
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise CampaignStoreError("workspace parent must be owner-private")
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise CampaignStoreError("workspace parent is a reparse point")
    if target.name in {"", ".", ".."}:
        raise CampaignStoreError("workspace filename required")
    if not target.exists() and not target.is_symlink():
        if not create:
            raise CampaignStoreError("workspace does not exist")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags, 0o600)
        except FileExistsError:
            # A simultaneous authorized creator won; validate that file below.
            pass
        else:
            os.close(descriptor)
    _private_file(target)
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = target.with_name(target.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            _private_file(sidecar)
    # Explicit path, URI interpretation disabled. Same-owner path replacement,
    # Windows ACL qualification and hostile filesystems are outside this boundary.
    db = sqlite3.connect(str(target), timeout=5.0, uri=False)
    try:
        db.execute("PRAGMA synchronous = FULL")
        db.execute("PRAGMA trusted_schema = OFF")
        yield CampaignStore(db)
    finally:
        db.close()


def main(
    argv: Sequence[str] | None = None, *,
    stdin: BinaryIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Source-bound GameForge narrative campaign and revision journal")
    commands = ("build", "verify", "play", "verify-play", "resume",
                "create-slot", "append-slot", "read-slot", "history")
    parser.add_argument("command", choices=commands)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    persistent = args.command in {"create-slot", "append-slot", "read-slot", "history"}
    if persistent != (args.database is not None):
        parser.error("database required only for persistent slot commands")
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        value = read_document(incoming)
        if args.command == "build":
            result = build_campaign(value)
        elif args.command == "play":
            data = _object(value, {"request", "actions"})
            result = play_campaign(data["request"], data["actions"])
        elif args.command == "resume":
            data = _object(value, {"request", "receipt", "additional"})
            result = append_actions(data["request"], data["receipt"], data["additional"])
        elif args.command in {"verify", "verify-play"}:
            data = _object(value, {"request", "receipt"})
            verifier = verify_campaign if args.command == "verify" else verify_session
            _require(verifier(data["request"], data["receipt"]), "independent campaign replay mismatch")
            result = {"verified": True, "native_qualified": False, "release_qualified": False}
        else:
            required = {"request", "slot"}
            optional: set[str] = set()
            if args.command in {"create-slot", "append-slot"}:
                required.add("operation")
            if args.command == "append-slot":
                required.update({"expected_revision", "additional"})
            if args.command == "read-slot":
                optional.add("revision")
            data = _object(value, required, optional)
            assert args.database is not None
            with open_workspace(args.database, create=args.command == "create-slot") as store:
                if args.command == "create-slot":
                    result = store.create(data["slot"], data["request"], data["operation"])
                elif args.command == "append-slot":
                    result = store.append(data["slot"], data["request"], data["expected_revision"],
                                          data["operation"], data["additional"])
                elif args.command == "read-slot":
                    result = store.read(data["slot"], data["request"], data.get("revision"))
                else:
                    result = store.history(data["slot"], data["request"])
        outgoing.write(_encode(result).decode("ascii") + "\n")
        return 0
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError,
            RecursionError, OSError, sqlite3.Error) as exc:
        errors.write("campaign rejected: " + type(exc).__name__ + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
