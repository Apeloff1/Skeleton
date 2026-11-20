#!/usr/bin/env python3
"""Opt-in physical synthetic Mongo crash/restart on private host scratch.

A *pinned already installed* Mongo image is run with --pull never,
--network none, a read-only container root and one randomly created
private host-owned scratch bind mounted at /data/db. A synthetic w:1,j:true
marker must survive SIGKILL, a real mongod restart, container removal and
a new container created on the SAME scratch directory.

This is stronger than tmpfs container/election tests but proves only
same-host synthetic file persistence and WiredTiger restart. No production
data, application volumes, external endpoints, replication majority,
cross-store coherence, device evidence or release authorization.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any

from scripts import local_ai_docker as host
from scripts import local_ai_offline_compose as binding
from scripts import qualify_local_ai_mongo_quorum_docker as quorum

SCHEMA = "skeleton.local-ai.docker.physical-synthetic-mongo-restart.v1"
_SCOPE = re.compile(r"skl-mongo-r-[a-f0-9]{16}\Z")
_CID = re.compile(r"[a-f0-9]{64}\Z")
_IMAGE = re.compile(r"sha256:[a-f0-9]{64}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_MAX_OUT = 16384
_DB = "skl_synthetic_crash_recovery"
_MONGO_URI = "mongodb://127.0.0.1:27017/?directConnection=true"
_MAX_SECS = 35


class SyntheticRestartError(host.LocalDockerError):
    """Real synthetic Mongo crash/restart lacks supported proof."""


def _scratch(scope: str) -> Path:
    """Create a single private, operator-owned scratch root (never input)."""
    if not _SCOPE.fullmatch(scope) or not isinstance(scope, str):
        raise SyntheticRestartError("synthetic scratch identity invalid")
    base = Path("/tmp")
    if not base.is_dir() or base.is_symlink():
        raise SyntheticRestartError("synthetic local scratch parent unavailable")
    try:
        path = Path(tempfile.mkdtemp(prefix=scope + "-", dir=str(base)))
        path.chmod(0o700)
        (path / "data").mkdir(mode=0o700)
        (path / ".owner").write_text(scope, encoding="ascii")
        (path / ".owner").chmod(0o600)
    except OSError:
        raise SyntheticRestartError("synthetic private scratch unavailable") from None
    _validate_scratch(path, scope)
    return path


def _validate_scratch(root: Path, scope: str) -> None:
    if (not isinstance(root, Path) or root.parent != Path("/tmp")
            or not re.fullmatch(
                re.escape(scope) + r"-[a-z0-9_]{8}", root.name
            )):
        raise SyntheticRestartError("synthetic scratch outside generated scope")
    try:
        root_meta = root.lstat()
        data_meta = (root / "data").lstat()
        marker = (root / ".owner").lstat()
        if (
            not stat.S_ISDIR(root_meta.st_mode)
            or not stat.S_ISDIR(data_meta.st_mode)
            or not stat.S_ISREG(marker.st_mode)
            or marker.st_nlink != 1
            or root_meta.st_mode & 0o077
            or data_meta.st_mode & 0o077
            or marker.st_mode & 0o077
            or not hasattr(os, "getuid")
            or any(row.st_uid != os.getuid() for row in (
                root_meta, data_meta, marker
            ))
            or marker.st_size != len(scope)
            or {item.name for item in root.iterdir()} != {"data", ".owner"}
            or (root / ".owner").read_text(encoding="ascii") != scope
        ):
            raise SyntheticRestartError("synthetic scratch is not exclusively owned")
    except (OSError, UnicodeError):
        raise SyntheticRestartError("synthetic scratch custody unavailable") from None


def _run_argv(scope: str, image: str, root: Path) -> list[str]:
    if not _SCOPE.fullmatch(scope) or not _IMAGE.fullmatch(image):
        raise SyntheticRestartError("synthetic Mongo pinned identity unavailable")
    _validate_scratch(root, scope)
    uid, gid = os.getuid(), os.getgid()
    if uid == 0 or gid == 0:
        raise SyntheticRestartError(
            "synthetic writable Mongo process requires non-root UID and GID"
        )
    user = f"{uid}:{gid}"
    return [
        "docker", "run", "-d", "--pull", "never",
        "--name", scope + "-node",
        "--label", "skeleton.synthetic-mongo-recovery=" + scope,
        "--network", "none",
        "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", user,
        "--memory", "768m", "--memory-swap", "768m",
        "--cpus", "1", "--pids-limit", "192",
        "--mount", f"type=bind,source={root / 'data'},target=/data/db",
        "--tmpfs", f"/tmp:rw,nosuid,nodev,uid={uid},gid={gid},mode=0700,size=16777216",
        "--tmpfs", f"/data/configdb:rw,nosuid,nodev,uid={uid},gid={gid},mode=0700,size=16777216",
        "-e", "HOME=/tmp",
        image, "mongod", "--bind_ip", "127.0.0.1", "--port", "27017",
        "--wiredTigerCacheSizeGB", "0.25",
        "--setParameter", "diagnosticDataCollectionEnabled=false",
    ]


def _admit(argv: list[str], *, scope: str, image: str, root: Path) -> None:
    """Reject any arbitrary Docker command even if called by later code."""
    if (not isinstance(argv, list) or not 2 <= len(argv) <= 64
            or any(type(a) is not str or not 0 < len(a) <= 8192
                   for a in argv)
            or argv[0] != "docker" or not _SCOPE.fullmatch(scope)
            or not _IMAGE.fullmatch(image)):
        raise SyntheticRestartError("unrecognized synthetic Docker operation")
    if argv[1] == "run":
        permitted = argv == _run_argv(scope, image, root)
    elif argv[1] == "ps":
        permitted = argv == [
            "docker", "ps", "--all", "--quiet", "--no-trunc",
            "--filter", "label=skeleton.synthetic-mongo-recovery=" + scope,
        ]
    elif argv[1] == "inspect":
        permitted = (len(argv) == 5
                     and argv[2:4] == ["--format", "{{json .}}"]
                     and bool(_CID.fullmatch(argv[4])))
    elif argv[1] == "kill":
        permitted = (len(argv) == 4
                     and argv[2] == "--signal=KILL"
                     and bool(_CID.fullmatch(argv[3])))
    elif argv[1] == "start":
        permitted = len(argv) == 3 and bool(_CID.fullmatch(argv[2]))
    elif argv[1] == "rm":
        permitted = (len(argv) == 4 and argv[2] == "--force"
                     and bool(_CID.fullmatch(argv[3])))
    elif argv[1] == "exec":
        permitted = (
            len(argv) == 9 and bool(_CID.fullmatch(argv[2]))
            and argv[3:8] == [
                "mongosh", "--quiet", "--norc", _MONGO_URI, "--eval",
            ] and argv[8].startswith("const x=(function(){")
            and argv[8].endswith('print("SKLPROBE:"+JSON.stringify(x));')
            and len(argv[8]) <= 4500
        )
    else:
        permitted = False
    if not permitted:
        raise SyntheticRestartError("Docker operation outside scoped synthetic authority")


def _call(argv: list[str], *, scope: str, image: str, root: Path,
          timeout: int = 40, allow_failure: bool = False) -> str:
    _admit(argv, scope=scope, image=image, root=root)
    try:
        result = subprocess.run(
            argv, text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SyntheticRestartError("synthetic local Docker execution unavailable") from None
    if (len(result.stdout) > _MAX_OUT or len(result.stderr) > _MAX_OUT):
        raise SyntheticRestartError("synthetic Docker diagnostic budget exceeded")
    if result.returncode != 0:
        if allow_failure:
            return ""
        raise SyntheticRestartError("synthetic Docker operation rejected") from None
    return result.stdout.strip()


def _json(raw: str) -> dict[str, Any]:
    if type(raw) is not str or not 0 < len(raw) < _MAX_OUT:
        raise SyntheticRestartError("synthetic Docker metadata absent or unbounded")
    def no_duplicate(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise SyntheticRestartError("synthetic Docker duplicate metadata")
            seen[key] = value
        return seen
    try:
        parsed = json.loads(raw, object_pairs_hook=no_duplicate,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, RecursionError):
        raise SyntheticRestartError("synthetic Docker metadata malformed") from None
    if not isinstance(parsed, dict):
        raise SyntheticRestartError("synthetic Docker inspection not an object")
    return parsed


def _inspect(cid: str, *, scope: str, image: str, root: Path,
             running: bool) -> None:
    doc = _json(_call([
        "docker", "inspect", "--format", "{{json .}}", cid,
    ], scope=scope, image=image, root=root))
    cfg, hostcfg, state = (doc.get("Config"), doc.get("HostConfig"),
                           doc.get("State"))
    if not all(isinstance(v, dict) for v in (cfg, hostcfg, state)):
        raise SyntheticRestartError("synthetic container metadata incomplete")
    mounts = doc.get("Mounts")
    if (doc.get("Id") != cid or doc.get("Name") != "/" + scope + "-node"
            or doc.get("Image") != image or cfg.get("Image") != image
            or cfg.get("User") != f"{os.getuid()}:{os.getgid()}"
            or (cfg.get("Labels") or {}).get(
                "skeleton.synthetic-mongo-recovery") != scope
            or state.get("Running") is not running
            or hostcfg.get("ReadonlyRootfs") is not True
            or hostcfg.get("CapAdd") not in (None, [])
            or hostcfg.get("Privileged") is not False
            or "ALL" not in (hostcfg.get("CapDrop") or [])
            or "no-new-privileges" not in (hostcfg.get("SecurityOpt") or [])
            or hostcfg.get("NetworkMode") != "none"
            or hostcfg.get("PortBindings") not in (None, {})
            or not isinstance(mounts, list) or len(mounts) != 1):
        raise SyntheticRestartError("synthetic container ownership or isolation mismatch")
    mount = mounts[0]
    if (not isinstance(mount, dict)
            or mount.get("Type") != "bind"
            or mount.get("Source") != str(root / "data")
            or mount.get("Destination") != "/data/db"
            or mount.get("RW") is not True):
        raise SyntheticRestartError("synthetic container mounted unapproved data")
    tmpfs = hostcfg.get("Tmpfs")
    expected_tmpfs = {
        "/tmp": 16777216, "/data/configdb": 16777216,
    }
    if not isinstance(tmpfs, dict) or set(tmpfs) != set(expected_tmpfs):
        raise SyntheticRestartError("synthetic private tmpfs mounts drifted")
    for name, size in expected_tmpfs.items():
        value = tmpfs[name]
        if type(value) is not str:
            raise SyntheticRestartError("synthetic tmpfs options invalid")
        options = value.split(",")
        params = dict(
            item.split("=", 1) if "=" in item else (item, "")
            for item in options
        )
        if (
            len(params) != len(options)
            or set(params) != {
                "rw", "nosuid", "nodev", "uid", "gid", "mode", "size",
            }
            or params["rw"] != "" or params["nosuid"] != ""
            or params["nodev"] != ""
            or params["uid"] != str(os.getuid())
            or params["gid"] != str(os.getgid())
            or params["mode"] not in ("0700", "700")
            or params["size"] != str(size)
        ):
            raise SyntheticRestartError("synthetic tmpfs ownership or quota drifted")
    if (type(hostcfg.get("Memory")) is not int
            or not 0 < hostcfg["Memory"] <= 805306368
            or type(hostcfg.get("MemorySwap")) is not int
            or hostcfg["MemorySwap"] != hostcfg["Memory"]
            or type(hostcfg.get("NanoCpus")) is not int
            or not 0 < hostcfg["NanoCpus"] <= 1000000000
            or type(hostcfg.get("PidsLimit")) is not int
            or not 0 < hostcfg["PidsLimit"] <= 192):
        raise SyntheticRestartError("synthetic restart exceeded cgroup admission")
    ns = (doc.get("NetworkSettings") or {})
    net = ns.get("Networks") if isinstance(ns, dict) else None
    ports = ns.get("Ports") if isinstance(ns, dict) else None
    if (not isinstance(net, dict)
            or set(net) not in (set(), {"none"})
            or (ports is not None and not isinstance(ports, dict))
            or (ports is not None and
                any(item not in (None, []) for item in ports.values()))
            or cfg.get("ExposedPorts") not in (
                None, {}, {"27017/tcp": {}}
            )):
        raise SyntheticRestartError("synthetic container reached external network")


def _shell(cid: str, expr: str, *, scope: str, image: str, root: Path,
           allow_failure: bool = False) -> dict[str, Any]:
    if (not _CID.fullmatch(cid) or type(expr) is not str
            or not 0 < len(expr) <= 3900):
        raise SyntheticRestartError("synthetic mongosh command invalid")
    js = 'const x=(function(){' + expr + '})();print("SKLPROBE:"+JSON.stringify(x));'
    result = _call([
        "docker", "exec", cid, "mongosh", "--quiet", "--norc",
        _MONGO_URI, "--eval", js,
    ], scope=scope, image=image, root=root,
       allow_failure=allow_failure, timeout=25)
    if not result and allow_failure:
        return {}
    lines = [
        line.removeprefix("SKLPROBE:")
        for line in result.splitlines()
        if line.startswith("SKLPROBE:")
    ]
    if len(lines) != 1:
        if allow_failure:
            return {}
        raise SyntheticRestartError("synthetic mongosh did not return one receipt")
    return _json(lines[0])


def _await_mongod(cid: str, *, scope: str, image: str, root: Path) -> None:
    expression = (
        "const r=db.adminCommand({hello:1});"
        "return {ready:r.ok===1 && r.isWritablePrimary===true};"
    )
    for _ in range(_MAX_SECS):
        if _shell(cid, expression, scope=scope, image=image, root=root,
                  allow_failure=True) == {"ready": True}:
            return
        time.sleep(1)
    raise SyntheticRestartError("synthetic mongod never became ready")


def _write(cid: str, token: str, *, scope: str, image: str, root: Path) -> None:
    if type(token) is not str or not re.fullmatch(r"[a-f0-9]{32}", token):
        raise SyntheticRestartError("synthetic challenge identity invalid")
    expr = (
        "const d=db.getSiblingDB('" + _DB + "');"
        "const r=d.runCommand({insert:'markers',"
        "documents:[{_id:'persistent-synthetic',token:'" + token + "',seq:1}],"
        "writeConcern:{w:1,j:true,wtimeout:10000}});"
        "return {ack:r.ok===1 && r.n===1 && !r.writeErrors && !r.writeConcernError};"
    )
    if _shell(cid, expr, scope=scope, image=image, root=root) != {"ack": True}:
        raise SyntheticRestartError("synthetic journaled write not acknowledged")


def _read(cid: str, token: str, *, scope: str, image: str, root: Path) -> None:
    if type(token) is not str or not re.fullmatch(r"[a-f0-9]{32}", token):
        raise SyntheticRestartError("synthetic challenge identity invalid")
    expr = (
        "const d=db.getSiblingDB('" + _DB + "');"
        "const r=d.runCommand({find:'markers',"
        "filter:{_id:'persistent-synthetic'},limit:2,readConcern:{level:'local'}});"
        "const a=(r.cursor&&r.cursor.firstBatch)||[];"
        "return {ok:r.ok===1,count:a.length,"
        "matched:a.length===1 && a[0].token==='" + token + "' && a[0].seq===1};"
    )
    if _shell(cid, expr, scope=scope, image=image, root=root) != {
        "ok": True, "count": 1, "matched": True,
    }:
        raise SyntheticRestartError(
            "journaled synthetic marker did not survive physical restart"
        )


def _owned_inspection(doc: dict[str, Any], *, cid: str, scope: str,
                      image: str, root: Path) -> bool:
    if (not isinstance(doc, dict) or doc.get("Id") != cid
            or doc.get("Name") != "/" + scope + "-node"
            or doc.get("Image") != image):
        return False
    cfg = doc.get("Config")
    if (not isinstance(cfg, dict)
            or cfg.get("Image") != image
            or (cfg.get("Labels") or {}).get(
                "skeleton.synthetic-mongo-recovery") != scope):
        return False
    hostcfg = doc.get("HostConfig")
    if (
        not isinstance(hostcfg, dict)
        or hostcfg.get("ReadonlyRootfs") is not True
        or hostcfg.get("NetworkMode") != "none"
        or hostcfg.get("PortBindings") not in (None, {})
        or hostcfg.get("Privileged") is not False
        or hostcfg.get("CapAdd") not in (None, [])
        or "ALL" not in (hostcfg.get("CapDrop") or [])
        or cfg.get("User") != f"{os.getuid()}:{os.getgid()}"
    ):
        return False
    mounts = doc.get("Mounts")
    return (
        isinstance(mounts, list) and len(mounts) == 1
        and isinstance(mounts[0], dict)
        and mounts[0].get("Type") == "bind"
        and mounts[0].get("Source") == str(root / "data")
        and mounts[0].get("Destination") == "/data/db"
        and mounts[0].get("RW") is True
    )


def _cleanup(scope: str, image: str, root: Path,
             known: set[str]) -> None:
    """Remove exact-name+label+image+bind owned nodes, then scratch only."""
    errors: list[str] = []
    discovered: set[str] = set()
    try:
        raw = _call([
            "docker", "ps", "--all", "--quiet", "--no-trunc",
            "--filter", "label=skeleton.synthetic-mongo-recovery=" + scope,
        ], scope=scope, image=image, root=root)
        discovered = set(raw.splitlines()) if raw else set()
        if any(not _CID.fullmatch(cid) for cid in discovered):
            raise SyntheticRestartError("untrusted synthetic container discovery")
    except SyntheticRestartError:
        errors.append("enumeration")
    for cid in sorted(discovered | known):
        try:
            raw = _call([
                "docker", "inspect", "--format", "{{json .}}", cid,
            ], scope=scope, image=image, root=root, allow_failure=True)
            if not raw:
                if cid in known:
                    errors.append("missing-known")
                continue
            if not _owned_inspection(
                _json(raw), cid=cid, scope=scope, image=image, root=root,
            ):
                errors.append("ownership")
                continue
            _call([
                "docker", "rm", "--force", cid,
            ], scope=scope, image=image, root=root)
        except SyntheticRestartError:
            errors.append("container")
    if errors:
        raise SyntheticRestartError(
            "synthetic Mongo cleanup incomplete: manually inspect scoped objects"
        )
    _validate_scratch(root, scope)
    if not shutil.rmtree.avoids_symlink_attacks:
        raise SyntheticRestartError("safe synthetic scratch cleanup unsupported")
    try:
        shutil.rmtree(root)
    except OSError:
        raise SyntheticRestartError(
            "synthetic scratch cleanup incomplete (no production state touched)"
        ) from None


def qualify_physical_synthetic_restart(
    mode: str, archive: Path, overlay_directory: Path, *,
    expected_receipt_sha256: str,
    allow_synthetic_writes: bool = False,
    allow_private_bind: bool = False,
    root: Path = host.ROOT,
) -> dict[str, object]:
    if allow_synthetic_writes is not True or allow_private_bind is not True:
        raise SyntheticRestartError(
            "both synthetic-only write and private scratch-bind approvals required"
        )
    admitted = binding.verify_binding(
        mode, archive, overlay_directory,
        expected_receipt_sha256=expected_receipt_sha256, root=root,
    )
    images = admitted.get("images")
    matches = [
        row.get("image_id") for row in images
        if isinstance(row, dict) and row.get("service") == "mongo"
    ] if isinstance(images, list) else []
    if (
        len(matches) != 1 or type(matches[0]) is not str
        or not _IMAGE.fullmatch(matches[0])
        or admitted.get("all_four_image_ids_installed") is not True
        or admitted.get("actual_overlay_render_verified") is not True
    ):
        raise SyntheticRestartError("immutable local Mongo image not independently bound")
    quorum._local_daemon()
    scope = "skl-mongo-r-" + secrets.token_hex(8)
    image = matches[0]
    scratch = _scratch(scope)
    known: set[str] = set()
    result = None
    failure = None
    try:
        argv = _run_argv(scope, image, scratch)
        cid = _call(argv, scope=scope, image=image, root=scratch, timeout=100)
        if not _CID.fullmatch(cid):
            raise SyntheticRestartError("Docker did not return a bounded unique container ID")
        known.add(cid)
        _inspect(cid, scope=scope, image=image, root=scratch, running=True)
        _await_mongod(cid, scope=scope, image=image, root=scratch)
        token = secrets.token_hex(16)
        _write(cid, token, scope=scope, image=image, root=scratch)
        _read(cid, token, scope=scope, image=image, root=scratch)

        _call([
            "docker", "kill", "--signal=KILL", cid,
        ], scope=scope, image=image, root=scratch)
        _inspect(cid, scope=scope, image=image, root=scratch, running=False)
        _call(["docker", "start", cid], scope=scope, image=image, root=scratch)
        _inspect(cid, scope=scope, image=image, root=scratch, running=True)
        _await_mongod(cid, scope=scope, image=image, root=scratch)
        _read(cid, token, scope=scope, image=image, root=scratch)

        _call(["docker", "rm", "--force", cid],
              scope=scope, image=image, root=scratch)
        known.discard(cid)
        successor = _call(_run_argv(scope, image, scratch),
                          scope=scope, image=image, root=scratch, timeout=100)
        if not _CID.fullmatch(successor) or successor == cid:
            raise SyntheticRestartError("new synthetic container identity not independently verified")
        known.add(successor)
        _inspect(successor, scope=scope, image=image, root=scratch, running=True)
        _await_mongod(successor, scope=scope, image=image, root=scratch)
        _read(successor, token, scope=scope, image=image, root=scratch)
        result = {
            "schema": SCHEMA,
            "status": "real_synthetic_mongo_journaled_restart_and_recreate_not_production_recovery",
            "pinned_offline_image_id_used": True,
            "registry_pull_requested": False,
            "docker_local_unix_endpoint_verified": True,
            "external_network_access": False,
            "host_ports_published": False,
            "only_private_generated_scratch_bind": True,
            "synthetic_journal_requested_w1_acknowledged": True,
            "synthetic_marker_survived_sigkill_and_restart": True,
            "synthetic_marker_survived_new_container_same_scratch": True,
            "private_scratch_cleanup_completed": False,
            "production_mongo_data_read_or_written": False,
            "production_volumes_attached": False,
            "actual_replica_majority_tested": False,
            "independent_physical_failure_domain_proven": False,
            "real_app_mongo_wiredtiger_recovery_qualified": False,
            "cross_store_snapshot_atomic": False,
            "protected_jeeves_chat_qualified": False,
            "release_authorized": False,
        }
    except Exception as exc:
        failure = exc
    try:
        _cleanup(scope, image, scratch, known)
    except SyntheticRestartError:
        raise
    if result is not None:
        result["private_scratch_cleanup_completed"] = True
    if failure is not None:
        raise SyntheticRestartError(
            "synthetic Mongo same-host physical restart failed; no application data accessed"
        ) from None
    assert result is not None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cpu", "nvidia", "rocm"), default="cpu")
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--overlay-directory", type=Path, required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    parser.add_argument("--allow-synthetic-database-writes", action="store_true")
    parser.add_argument("--allow-private-synthetic-bind", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = qualify_physical_synthetic_restart(
            args.mode, args.directory, args.overlay_directory,
            expected_receipt_sha256=args.expected_receipt_sha256,
            allow_synthetic_writes=args.allow_synthetic_database_writes,
            allow_private_bind=args.allow_private_synthetic_bind,
        )
    except SyntheticRestartError:
        print("synthetic Mongo same-host restart: DENIED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
