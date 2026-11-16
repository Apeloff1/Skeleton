"""Persistent, redacted intent for an uncertain Compose operation.

OS locks alone cannot prove an interrupted Docker command has finished.
A cooperating installer must preserve this record until a normal process
exit or explicit operator acknowledgment. No recovery command runs Docker.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import stat
import uuid

from skeleton.app.runtime_operation import RuntimeOperationDenied, runtime_operation

PENDING_NAME = ".env.operation.pending"
SCHEMA = "skeleton.app.runtime_mutation.v1"
_MAX = 1024
_ID = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_SCOPES = {"install": {"compose-start", "setup-ui-recovery"},
           "start": {"compose-start"}, "stop": {"compose-stop"}}
_MUTATIONS = frozenset().union(*_SCOPES.values())


def _stamp(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400
            or not 0 <= info.st_size <= _MAX
            or (os.name != "nt" and (info.st_uid != os.geteuid()
                                      or stat.S_IMODE(info.st_mode) != 0o600))):
        raise RuntimeOperationDenied("pending mutation record unsafe; preserve it")
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate record field")
        result[key] = value
    return result


def _owner(lease):
    if not lease.current():
        raise RuntimeOperationDenied("runtime operation custody changed")


def pending(lease):
    _owner(lease)
    path = lease.root / PENDING_NAME
    try:
        try:
            initial = _stamp(path.lstat())
        except FileNotFoundError:
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(fd, "rb") as handle:
            before = _stamp(os.fstat(handle.fileno()))
            raw = handle.read(_MAX + 1)
            after = _stamp(os.fstat(handle.fileno()))
        if before != initial or before != after or after != _stamp(path.lstat()) or len(raw) != before[4]:
            raise ValueError("record changed")
        data = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
        if (type(data) is not dict or set(data) != {"schema","id","mutation","root","lock"}
                or data["schema"] != SCHEMA or type(data["id"]) is not str
                or _ID.fullmatch(data["id"]) is None
                or type(data["mutation"]) is not str or data["mutation"] not in _MUTATIONS
                or any(type(data[k]) is not list or len(data[k]) != 2
                       or any(type(v) is not int or v < 0 for v in data[k])
                       for k in ("root","lock"))
                or tuple(data["root"]) != lease.directory_identity
                or tuple(data["lock"]) != lease.file_identity):
            raise ValueError("record identity invalid")
        _owner(lease)
        return data, after
    except (OSError, ValueError, RecursionError, UnicodeError):
        raise RuntimeOperationDenied("pending mutation record unverified; preserve it") from None


def _flush_directory(lease):
    # No portable directory fsync on Windows. File bytes are flushed there;
    # power-loss directory publication remains separately unqualified.
    if os.name == "nt":
        return
    fd = os.open(lease.root, os.O_RDONLY | getattr(os,"O_DIRECTORY",0)
                 | getattr(os,"O_NOFOLLOW",0))
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != lease.directory_identity:
            raise RuntimeOperationDenied("runtime operation root changed")
        os.fsync(fd)
    finally:
        os.close(fd)


def begin(lease, mutation):
    if mutation not in _SCOPES.get(lease.operation, ()):
        raise RuntimeOperationDenied("mutation is outside runtime operation scope")
    if pending(lease) is not None:
        raise RuntimeOperationDenied("previous runtime mutation unresolved; inspect runtime-recovery status")
    data = {"schema":SCHEMA,"id":uuid.uuid4().hex,"mutation":mutation,
            "root":list(lease.directory_identity),"lock":list(lease.file_identity)}
    raw = json.dumps(data, sort_keys=True, separators=(",",":")).encode("ascii")
    try:
        descriptor = os.open(lease.root / PENDING_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os,"O_NOFOLLOW",0) | getattr(os,"O_BINARY",0), 0o600)
        with os.fdopen(descriptor,"wb") as handle:
            if handle.write(raw) != len(raw):
                raise OSError("short record")
            handle.flush()
            os.fsync(handle.fileno())
        _flush_directory(lease)
    except OSError:
        # Never delete incomplete evidence automatically.
        raise RuntimeOperationDenied("mutation intent publication uncertain; preserve record") from None
    observed = pending(lease)
    if observed is None or observed[0] != data:
        raise RuntimeOperationDenied("mutation intent changed before dispatch")
    return observed


def clear(lease, expected):
    if expected is None or pending(lease) != expected:
        raise RuntimeOperationDenied("mutation record changed; preserve it")
    path = lease.root / PENDING_NAME
    try:
        _owner(lease)
        if _stamp(path.lstat()) != expected[1]:
            raise RuntimeOperationDenied("mutation record changed; preserve it")
        path.unlink()
        _flush_directory(lease)
    except OSError:
        raise RuntimeOperationDenied("mutation completion publication uncertain") from None


def run_mutation(lease, mutation, runner, *args, **kwargs):
    record = begin(lease, mutation)
    if pending(lease) != record:
        raise RuntimeOperationDenied("mutation record changed before dispatch")
    completed = runner(*args, **kwargs)
    # Timeouts, crashes, signals, OS errors or malformed results retain intent.
    status = getattr(completed, "returncode", None)
    if type(status) is int and 0 <= status <= 255:
        clear(lease, record)
    return completed


def recovery_status(root: Path):
    with runtime_operation(root, "recover") as lease:
        record = pending(lease)
        return {"schema":"skeleton.app.runtime_recovery_status.v1",
                "pending":record is not None,
                "operation_id":record[0]["id"] if record else None,
                "mutation":record[0]["mutation"] if record else None,
                "daemon_idle_verified":False,"automatic_retry_permitted":False,
                "persistent_application_data_modified":False}


def acknowledge(root: Path, operation_id: str, *, daemon_inspected: bool):
    if (daemon_inspected is not True or type(operation_id) is not str
            or _ID.fullmatch(operation_id) is None):
        raise RuntimeOperationDenied("exact operation identity and explicit daemon inspection required")
    with runtime_operation(root, "recover") as lease:
        record = pending(lease)
        if record is None or record[0]["id"] != operation_id:
            raise RuntimeOperationDenied("pending mutation identity does not match")
        clear(lease, record)
        return {"schema":"skeleton.app.runtime_recovery_status.v1","pending":False,
                "operation_id":operation_id,"acknowledged":True,"daemon_idle_verified":False,
                "automatic_retry_permitted":False,"persistent_application_data_modified":False}


def main(argv, *, root: Path):
    parser = argparse.ArgumentParser(prog="runtime-recovery",
        description="Inspect uncertain runtime intent; never run Docker or retry automatically.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    ack = commands.add_parser("acknowledge")
    ack.add_argument("operation_id")
    ack.add_argument("--daemon-inspected",action="store_true",
                     help="confirm inspection of the selected Docker project, daemon and persistent data")
    args = parser.parse_args(argv)
    try:
        result = (recovery_status(root) if args.command == "status" else
                  acknowledge(root,args.operation_id,daemon_inspected=args.daemon_inspected))
    except RuntimeOperationDenied as exc:
        print(json.dumps({"ok":False,"message":str(exc)},sort_keys=True))
        return 1
    print(json.dumps({"ok":True,**result},sort_keys=True))
    return 0
