"""Real-daemon ephemeral cold-volume Docker execution qualification.

CI ONLY: builds a pinned Python worker containing the canonical copy module,
creates a disposable synthetic Compose-labeled volume, checks the physical
daemon path, streams actual bytes over a READONLY bind mount with network
disabled, independently verifies them in another container, deliberately
corrupts the disposable archive, and verifies that tampering fails.

No real application volumes, accounts, GGUF, network inference or credentials
are accessed. Never assert MongoDB consistency, recoverability or guarded chat.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts import local_ai_cold_backup as cold
from scripts import local_ai_recovery as recovery
from scripts import local_ai_volume_copy as worker
from scripts import local_ai_docker as host

_SCHEMA = "skeleton.local-ai.docker-ephemeral-cold-copy-acceptance.v1"
_BASE = re.compile(r"ARG PYTHON_IMAGE=(python:[^\s]+@sha256:[0-9a-f]{64})")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")


_FAILURE_STAGES = frozenset((
    "docker-daemon", "worker-build", "worker-image", "volume-create",
    "synthetic-seed", "archive-tamper-setup", "docker-run",
    "worker-copy", "worker-rehash", "synthetic-volume-identity",
    "worker-copy-rejected", "worker-copy-io", "worker-copy-source-mutated",
    "worker-copy-ok", "worker-copy-probe-unavailable",
    "synthetic-attachment-inventory", "mount-preflight", "unclassified",
))


class EphemeralDockerAcceptanceError(RuntimeError):
    """A disposable physical Docker copy or negative test did not qualify."""


def _safe_call(
    command: list[str], *, timeout: int = 150,
    stage_override: str | None = None,
) -> str:
    stage = "unclassified"
    if command[:2] == ["docker", "info"]:
        stage = "docker-daemon"
    elif command[:2] == ["docker", "build"]:
        stage = "worker-build"
    elif command[:3] == ["docker", "image", "inspect"]:
        stage = "worker-image"
    elif command[:3] == ["docker", "volume", "create"]:
        stage = "volume-create"
    elif command[:2] == ["docker", "run"]:
        # Only fixed non-sensitive operation names, never Docker stderr.
        stage = (
            "synthetic-seed" if "SYNTHETIC-COLD" in str(command[-1])
            else "archive-tamper-setup" if "TAMPER" in str(command[-1])
            else "docker-run"
        )
    if stage_override is not None:
        if stage_override not in _FAILURE_STAGES:
            raise EphemeralDockerAcceptanceError("unclassified")
        stage = stage_override
    try:
        proc = subprocess.run(
            command, text=True, capture_output=True,
            check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise EphemeralDockerAcceptanceError(stage) from None
    if proc.returncode != 0 or len(proc.stdout) > 8192:
        raise EphemeralDockerAcceptanceError(stage) from None
    return proc.stdout.strip()


def _fail_command(command: list[str], *, timeout: int = 45) -> None:
    try:
        proc = subprocess.run(
            command, text=True, capture_output=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise EphemeralDockerAcceptanceError("Docker failure scenario unavailable") from None
    if proc.returncode == 0:
        raise EphemeralDockerAcceptanceError("disposable Docker hostile case unexpectedly succeeded")


def _image_base(repo: Path) -> str:
    try:
        source = (repo / "Dockerfile").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise EphemeralDockerAcceptanceError("canonical Dockerfile unavailable") from None
    match = _BASE.search(source)
    if match is None:
        raise EphemeralDockerAcceptanceError("canonical Python image is not SHA-pinned")
    return match.group(1)


def _build_worker(context: Path, image: str, repo: Path) -> str:
    context.mkdir(mode=0o700)
    (context / "scripts").mkdir(mode=0o700)
    shutil.copyfile(
        repo / "scripts/local_ai_volume_copy.py",
        context / "scripts/local_ai_volume_copy.py",
    )
    (context / "scripts/__init__.py").write_text("", encoding="utf-8")
    base = _image_base(repo)
    (context / "Dockerfile").write_text(
        "FROM " + base + "\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "WORKDIR /app\n"
        "COPY scripts /app/scripts\n",
        encoding="utf-8",
    )
    _safe_call(["docker", "build", "--pull", "--quiet", "-t", image, str(context)],
               timeout=600)
    sha = _safe_call(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image]
    )
    if not _SHA.fullmatch(sha):
        raise EphemeralDockerAcceptanceError("ephemeral worker image has no digest identity")
    return sha


def _seed(volume: str, image: str) -> None:
    # Only synthetic non-sensitive data inside this ephemeral CI volume.
    code = (
        "from pathlib import Path\n"
        "root=Path('/source')\n"
        "(root/'journal').mkdir(exist_ok=False)\n"
        "(root/'WiredTiger.wt').write_bytes(b'SYNTHETIC-COLD'*(350000))\n"
        "(root/'journal'/'fixture.wt').write_bytes(b'JOURNAL'*(2048))\n"
    )
    _safe_call([
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--read-only", "--user=0:0",
        "--mount=type=volume,source=" + volume + ",target=/source",
        "--entrypoint=python", image, "-c", code,
    ])


def _probe_existing_readonly_bind(
    image_id: str, daemon_path: str, archive: Path,
) -> None:
    """Execute one real restricted container without modifying any volume."""
    code = (
        "from pathlib import Path\n"
        "import scripts.local_ai_volume_copy as worker\n"
        "assert worker.SCHEMA.startswith('skeleton.local-ai.docker')\n"
        "assert Path('/source/WiredTiger.wt').stat().st_size > 4000000\n"
        "assert Path('/archive').is_dir()\n"
    )
    _safe_call([
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user=0:0",
        "--memory=4g", "--cpus=2", "--pids-limit=96",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
        "--mount=type=bind,source=" + daemon_path + ",target=/source,readonly",
        "--mount=type=bind,source=" + str(archive) + ",target=/archive",
        "--entrypoint=python", image_id, "-c", code,
    ], stage_override="mount-preflight")


def _corrupt_disposable_archive(archive: Path, image_id: str) -> None:
    code = (
        "from pathlib import Path\n"
        "p=Path('/archive/mongo_data/WiredTiger.wt')\n"
        "p.write_bytes(p.read_bytes() + b'TAMPER')\n"
    )
    _safe_call([
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user=0:0",
        "--mount=type=bind,source=" + str(archive) + ",target=/archive",
        "--entrypoint=python", image_id, "-c", code,
    ])



# These are public, fixed stage codes, never daemon text or user-volume paths.
_COPY_PROBE_CODES = frozenset((
    "worker-copy-rejected", "worker-copy-io", "worker-copy-source-mutated",
    "worker-copy-ok", "worker-copy-probe-unavailable",
))


def _probe_failed_worker_copy(image_id: str, daemon_path: str, scratch: Path) -> str:
    """Diagnose *only* the disposable synthetic CI volume after an actual failure.

    Use a different destination to preserve the first attempt's partial
    evidence. This probe is read-only against the same synthetic source, has
    no network or privileged capabilities, and prints a fixed enum only.
    The original worker failure remains a failure regardless of this result.
    """
    diagnostic = scratch / "worker-diagnostic"
    diagnostic.mkdir(mode=0o700)
    script = (
        "from pathlib import Path\n"
        "from scripts import local_ai_volume_copy as copy\n"
        "try:\n"
        "  copy.copy_volume('mongo_data', Path('/source'), Path('/archive'))\n"
        "except copy.VolumeCopyError as error:\n"
        "  if str(error) == 'source changed while copying offline archive':\n"
        "    print('worker-copy-source-mutated')\n"
        "  else:\n"
        "    print('worker-copy-rejected')\n"
        "except (OSError, ValueError, TypeError):\n"
        "  print('worker-copy-io')\n"
        "else:\n"
        "  print('worker-copy-ok')\n"
    )
    try:
        result = _safe_call([
            "docker", "run", "--rm", "--pull=never", "--network=none",
            "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=0:0",
            "--memory=4g", "--cpus=2", "--pids-limit=96",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
            "--mount=type=bind,source=" + daemon_path + ",target=/source,readonly",
            "--mount=type=bind,source=" + str(diagnostic) + ",target=/archive",
            "--entrypoint=python", image_id, "-c", script,
        ], stage_override="worker-copy")
    except EphemeralDockerAcceptanceError:
        return "worker-copy-probe-unavailable"
    return result if result in _COPY_PROBE_CODES else "worker-copy-probe-unavailable"


def qualify_ephemeral_cold_copy(repo: Path) -> dict[str, object]:
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("CI") != "true"
            or os.getenv("GITHUB_REPOSITORY") != "Apeloff1/Skeleton"):
        raise EphemeralDockerAcceptanceError("physical qualification allowed only in the repository's disposable CI")
    if not (repo / "scripts/local_ai_volume_copy.py").is_file():
        raise EphemeralDockerAcceptanceError("canonical archive worker missing")
    _safe_call(["docker", "info", "--format", "{{.ServerVersion}}"])
    token = secrets.token_hex(10)
    project = "ci-skeleton-" + token
    logical = "mongo_data"
    volume = project + "-" + logical
    worker_name = "skeleton-local-cold-ci:" + token
    created = False
    built = False
    with tempfile.TemporaryDirectory(prefix="skeleton-docker-cold-ci-") as temp:
        scratch = Path(temp)
        context = scratch / "build-context"
        archive = scratch / "archive"
        archive.mkdir(mode=0o700)
        try:
            image_id = _build_worker(context, worker_name, repo)
            built = True
            result = _safe_call([
                "docker", "volume", "create",
                "--label=com.docker.compose.project=" + project,
                "--label=com.docker.compose.volume=" + logical,
                volume,
            ])
            if result != volume:
                raise EphemeralDockerAcceptanceError("disposable volume identity differs")
            created = True
            _seed(volume, image_id)
            try:
                daemon_path = recovery._volume_metadata(volume, logical, project, repo)
            except host.LocalDockerError:
                raise EphemeralDockerAcceptanceError("synthetic-volume-identity") from None
            try:
                active = recovery._running_attachments(volume, repo)
            except host.LocalDockerError:
                raise EphemeralDockerAcceptanceError("synthetic-attachment-inventory") from None
            if active:
                raise EphemeralDockerAcceptanceError("synthetic-attachment-inventory")
            _probe_existing_readonly_bind(image_id, daemon_path, archive)
            try:
                copied = cold._run_worker(
                    image_id, logical, volume, archive, action="copy", root=repo,
                    source_mountpoint=daemon_path,
                )
            except host.LocalDockerError:
                raise EphemeralDockerAcceptanceError(
                    _probe_failed_worker_copy(image_id, daemon_path, scratch)
                ) from None
            try:
                independently_rehashed = cold._run_worker(
                    image_id, logical, None, archive, action="verify", root=repo,
                )
            except host.LocalDockerError:
                raise EphemeralDockerAcceptanceError("worker-rehash") from None
            if copied != independently_rehashed or copied["files"] != 2:
                raise EphemeralDockerAcceptanceError("worker-rehash")
            # Prove Docker does NOT auto-create an absent volume on the new
            # readonly type=bind source path, unlike type=volume.
            missing = "ci-absent-" + token
            absent = "/var/lib/docker/volumes/" + missing + "/_data"
            try:
                cold._run_worker(
                    image_id, logical, missing, archive, action="copy", root=repo,
                    source_mountpoint=absent,
                )
            except host.LocalDockerError:
                pass
            else:
                raise EphemeralDockerAcceptanceError("Docker created a nonexistent readonly source")
            _fail_command(["docker", "volume", "inspect", missing])
            _corrupt_disposable_archive(archive, image_id)
            try:
                cold._run_worker(
                    image_id, logical, None, archive, action="verify", root=repo,
                )
            except host.LocalDockerError:
                pass
            else:
                raise EphemeralDockerAcceptanceError("physical corrupted archive rehash succeeded")
            return {
                "schema": _SCHEMA,
                "status": "ephemeral_docker_volume_cold_bytes_and_tamper_denial_verified",
                "real_docker_daemon_executed": True,
                "actual_model_inference_executed": False,
                "sampled_volumes": 1,
                "sampled_files": copied["files"],
                "sampled_bytes": copied["bytes"],
                "missing_source_created": False,
                "corrupt_archive_rejected": True,
                "real_application_volume_accessed": False,
                "mongo_database_consistency_qualified": False,
                "application_restore_qualified": False,
                "guarded_jeeves_qualified": False,
            }
        finally:
            # These names are generated exclusively in this invocation and
            # never derive from any existing application Compose project.
            if created:
                subprocess.run(["docker", "volume", "rm", volume],
                               capture_output=True, check=False, timeout=45)
            if built:
                subprocess.run(["docker", "image", "rm", worker_name],
                               capture_output=True, check=False, timeout=45)


def main() -> int:
    try:
        print(json.dumps(
            qualify_ephemeral_cold_copy(Path(__file__).resolve().parents[1]),
            sort_keys=True,
        ))
        return 0
    except (EphemeralDockerAcceptanceError, host.LocalDockerError) as error:
        stage = str(error) if str(error) in _FAILURE_STAGES else "unclassified"
        print(json.dumps({
            "ok": False,
            "stage": stage,
            "error": "ephemeral physical Docker cold archive qualification unavailable",
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
