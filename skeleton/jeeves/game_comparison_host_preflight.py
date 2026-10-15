"""Fail-closed host prerequisites for actually launching isolated native emulators.

The existing source/core readiness doctor does not mean a worker can start.
This assessment checks the trusted system interpreter, Linux bubblewrap,
worker scripts and (optionally) exercises an ephemeral sandbox containing
*only* /usr/bin/true. No core, firmware, ROM or game process is launched.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from .game_comparison_schema import digest

SCHEMA="skeleton.game.comparison_native_host_preflight.v1"
SANDBOX_PROBE_TIMEOUT=8


def inspect_native_host_runtime(*, probe_sandbox: bool=False) -> dict[str,Any]:
    if type(probe_sandbox) is not bool:
        raise ValueError("Host sandbox execution probe must be explicitly enabled or disabled")
    findings=[]
    platform=sys.platform
    linux=platform.startswith("linux")
    if not linux:
        findings.append({
            "code":"native_host_requires_linux",
            "severity":"blocker",
            "remedy":"Run the isolated libretro worker on Linux or implement and qualify a Windows-native sandbox host",
        })
    interpreter=Path("/usr/bin/python3")
    trusted=False
    python_sha=None
    try:
        canonical=interpreter.resolve(strict=True)
        owner=canonical.stat()
        trusted=(canonical.is_relative_to(Path("/usr"))
                 and owner.st_uid==0 and not owner.st_mode & 0o022
                 and bool(owner.st_mode & 0o111) and stat.S_ISREG(owner.st_mode))
        if trusted:
            # Align with native host's strict 64 MiB interpreter byte budget.
            if owner.st_size>64*1024*1024:
                trusted=False
            else:
                import hashlib
                h=hashlib.sha256()
                with canonical.open("rb") as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b""):
                        h.update(chunk)
                python_sha=h.hexdigest()
    except OSError:
        trusted=False
    if not trusted:
        findings.append({
            "code":"trusted_system_python_missing",
            "severity":"blocker",
            "remedy":"Install a root-owned non-writable /usr/bin/python3 interpreter under /usr compatible with the emulator worker",
        })
    bwrap=shutil.which("bwrap") if linux else None
    sandbox_binary=None
    if bwrap:
        try:
            path=Path(bwrap).resolve(strict=True)
            info=path.stat()
            if stat.S_ISREG(info.st_mode) and bool(info.st_mode & 0o111):
                sandbox_binary=str(path)
        except OSError:
            sandbox_binary=None
    if sandbox_binary is None:
        findings.append({
            "code":"bubblewrap_missing",
            "severity":"blocker",
            "remedy":"Install Linux bubblewrap (bwrap) and enable required user namespaces for the actual account",
        })
    worker_root=Path(__file__).parent
    worker_names=("game_emulator_worker.py","game_emulator_protocol.py")
    worker_files=[]
    for name in worker_names:
        path=worker_root/name
        try:
            st=path.stat()
            good=stat.S_ISREG(st.st_mode) and 0<st.st_size<=1024*1024
        except OSError:
            good=False
        worker_files.append({"name":name,"present_bounded_source":good})
        if not good:
            findings.append({
                "code":"worker_module_missing",
                "severity":"blocker",
                "module":name,
                "remedy":"Restore the matching pinned source module in the installed application",
            })
    probe={
        "requested":probe_sandbox,
        "attempted":False,
        "passed":False,
        "status":"not_requested" if not probe_sandbox else "blocked_before_probe",
    }
    static_ready=not findings
    if probe_sandbox and static_ready:
        probe["attempted"]=True
        # Uses the same isolation primitives as the worker, with *no* game
        # content, model, firmware or app-specific mounts.
        argv=[
            sandbox_binary,"--unshare-all","--die-with-parent",
            "--clearenv","--cap-drop","ALL",
            "--ro-bind","/usr","/usr",
            "--ro-bind-try","/lib","/lib",
            "--ro-bind-try","/lib64","/lib64",
            "--proc","/proc","--dev","/dev",
            "--",str(Path("/usr/bin/true").resolve(strict=True)),
        ]
        try:
            process=subprocess.run(
                argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=SANDBOX_PROBE_TIMEOUT,
                check=False,env={"PATH":"/usr/bin:/bin"},
            )
            probe["passed"]=process.returncode==0
            probe["status"]="sandbox_syscall_probe_passed" if probe["passed"] else "sandbox_syscall_probe_failed"
        except (OSError,subprocess.TimeoutExpired):
            probe["status"]="sandbox_syscall_probe_unavailable"
        if not probe["passed"]:
            findings.append({
                "code":"bubblewrap_user_namespace_probe_failed",
                "severity":"blocker",
                "remedy":"Allow user namespaces and confirm bwrap can launch a minimal isolated /usr/bin/true process",
            })
    report={
        "schema_version":SCHEMA,
        "platform":platform,
        "trusted_interpreter_sha256":python_sha,
        "bubblewrap_found":sandbox_binary is not None,
        "worker_modules":worker_files,
        "static_host_launch_prerequisites_satisfied":static_ready,
        "sandbox_probe":probe,
        "native_launch_preflight_passed":not findings and (not probe_sandbox or probe["passed"]),
        "native_rom_booted":False,
        "actual_controller_accuracy_verified":False,
        "windows_native_executor_present":False,
        "blockers":findings,
    }
    report["host_preflight_sha256"]=digest(report)
    return report
