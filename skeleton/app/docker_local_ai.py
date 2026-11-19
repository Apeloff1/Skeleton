"""Docker-facing operator commands for Skeleton's EXISTING governed local GGUF owner.

Not a provider, downloader, second inference server or model trainer. The host
launcher runs these commands with --network none; application startup keeps the
canonical provider/runtime guard and five-service topology.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Sequence

from skeleton.ai.runtime.inference.deployment import (
    LocalModelDeployment,
    LocalModelDeploymentError,
    create_local_model_deployment,
    qualify_local_model_deployment_sync,
)

MODEL_ROOT = Path("/app/local-ai")
MANIFEST_NAME = "jeeves.json"
MODEL_ID = "jeeves"
PROFILES = ("raw", "llama-completion-chat", "qwen3-completion-chat")
REMOTE_KEYS = (
    "OPENAI_API_KEY",
    "EMERGENT_LLM_KEY",
    "AI_SECONDARY_API_KEY",
    "AI_SECONDARY_BASE_URL",
    "AI_SECONDARY_MODEL",
    "AI_VERIFICATION_MODEL",
)


class DockerLocalAIError(ValueError):
    """The operator request cannot be admitted as a local Jeeves deployment."""


def _directory(root: Path) -> Path:
    """Avoid path redirection through a symlinked provisioner mount."""
    try:
        mode = root.lstat().st_mode
    except OSError as exc:
        raise DockerLocalAIError("model mount is unavailable") from exc
    if not stat.S_ISDIR(mode) or root.is_symlink():
        raise DockerLocalAIError("model mount must be a real directory")
    return root.resolve(strict=True)


def _member(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    """Validate operator-supplied POSIX mount-relative paths before any I/O."""
    if (
        not isinstance(relative, str)
        or not relative
        or "\\" in relative
        or "\x00" in relative
    ):
        raise DockerLocalAIError("invalid model mount relative path")
    candidate = Path(relative)
    if (
        candidate.is_absolute()
        or any(part in ("", ".", "..") for part in relative.split("/"))
        or len(candidate.parts) > 16
        or len(relative) > 512
    ):
        raise DockerLocalAIError("model file must be a bounded mount-relative path")
    member = root.joinpath(*candidate.parts)
    # Verify each existing component without resolving a redirected target.
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise DockerLocalAIError("model mount may not contain symlinked paths")
        if not cursor.exists():
            if must_exist:
                raise DockerLocalAIError("model artifact is unavailable")
            if cursor != member:
                raise DockerLocalAIError("manifest parent directory is unavailable")
        elif cursor != member and not cursor.is_dir():
            raise DockerLocalAIError("model artifact parent must be a directory")
    if must_exist:
        try:
            if not stat.S_ISREG(member.lstat().st_mode):
                raise DockerLocalAIError("model artifact must be a regular file")
        except OSError as exc:
            raise DockerLocalAIError("model artifact cannot be inspected") from exc
    return member


def _manifest(root: Path) -> Path:
    return _member(root, MANIFEST_NAME, must_exist=False)


def _environment_guard(path: Path) -> None:
    expected = {
        "AI_PROVIDER": "local",
        "AI_MODEL": MODEL_ID,
        "AI_LOCAL_DEPLOYMENT_PATH": str(path),
        "AI_LOCAL_MODEL_PATH": "",
        "AI_LOCAL_MODEL_CATALOG_PATH": "",
        "JEEVES_LOCAL_ONLY": "1",
        "AI_LOCAL_GUARD_REQUIRED": "1",
        "JEEVES_PRIMARY_MODEL_ID": MODEL_ID,
    }
    for key, wanted in expected.items():
        if os.environ.get(key, "") != wanted:
            raise DockerLocalAIError("container local-only environment fence failed")
    if any(os.environ.get(key, "").strip() for key in REMOTE_KEYS):
        raise DockerLocalAIError("hosted or secondary model credentials are configured")


def inspect_deployment(*, require_env: bool = False, root: Path = MODEL_ROOT) -> dict[str, object]:
    root = _directory(root)
    path = _member(root, MANIFEST_NAME)
    if require_env:
        _environment_guard(path)
    deployment = LocalModelDeployment.load(path)
    if deployment.model_id != MODEL_ID or deployment.runtime_kind != "llama.cpp-cli":
        raise DockerLocalAIError("manifest must identify exactly one Jeeves GGUF runtime")
    # Canonical load verifies hashes. Additionally require a hermetic mount for
    # executable and weights; an operator cannot point into host secrets or /usr.
    for value in (deployment.executable_path, deployment.model_path):
        try:
            relative = value.relative_to(root)
        except ValueError as exc:
            raise DockerLocalAIError("deployment references a file outside the model mount") from exc
        if len(relative.parts) == 0:
            raise DockerLocalAIError("deployment artifact is invalid")
        if _member(root, relative.as_posix()) != value:
            raise DockerLocalAIError("deployment artifact resolution differs")
    limit_path = Path("/sys/fs/cgroup/memory.max")
    try:
        raw_limit = limit_path.read_text(encoding="ascii").strip()
        cgroup_limit = int(raw_limit) if raw_limit.isdecimal() else None
    except (OSError, ValueError):
        cgroup_limit = None
    return {
        "schema": "skeleton.local-ai.docker.preflight.v1",
        "status": "artifact_verified_not_inference_qualified",
        "provider": "local",
        "model_id": deployment.model_id,
        "model_sha256": deployment.model_sha256,
        "executable_sha256": deployment.executable_sha256,
        "manifest_sha256": deployment.manifest_digest,
        "model_bytes": deployment.model_path.stat().st_size,
        "context_size": deployment.context_size,
        "gpu_layers_requested": deployment.gpu_layers or 0,
        "cgroup_memory_limit_bytes": cgroup_limit,
        "cgroup_coverage": "reported_not_qualified",
        "network_required": False,
        "inference_executed": False,
    }


def pin_deployment(
    *, model: str, executable: str, profile: str, context: int,
    threads: int | None, gpu_layers: int, root: Path = MODEL_ROOT,
) -> dict[str, object]:
    root = _directory(root)
    if profile not in PROFILES or not 256 <= context <= 131072:
        raise DockerLocalAIError("unsupported completion profile or context")
    if threads is not None and not 1 <= threads <= 256:
        raise DockerLocalAIError("thread count must be in [1, 256]")
    if not 0 <= gpu_layers <= 1024:
        raise DockerLocalAIError("GPU layer count must be in [0, 1024]")
    dest = _manifest(root)
    if dest.exists() or dest.is_symlink():
        raise DockerLocalAIError("existing Jeeves pin is immutable; keep it and choose explicit migration")
    executable_path = _member(root, executable)
    model_path = _member(root, model)
    deployment = create_local_model_deployment(
        dest, executable_path=executable_path, model_path=model_path,
        model_id=MODEL_ID, runtime_profile=profile,
        context_size=context, threads=threads, gpu_layers=gpu_layers,
    )
    admitted = inspect_deployment(root=root)
    if admitted["model_sha256"] != deployment.model_sha256:
        raise DockerLocalAIError("newly created pin did not survive verification")
    return {**admitted, "status": "pinned_not_inference_qualified"}


def qualify_deployment(*, max_output_tokens: int = 32, root: Path = MODEL_ROOT) -> dict[str, object]:
    inspect_deployment(root=root)
    if not 1 <= max_output_tokens <= 128:
        raise DockerLocalAIError("qualification output token limit must be in [1, 128]")
    return qualify_local_model_deployment_sync(
        _member(_directory(root), MANIFEST_NAME),
        prompt="Respond with a brief offline Jeeves acknowledgement.",
        max_output_tokens=max_output_tokens,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pin = sub.add_parser("pin", help="Create one immutable Jeeves deployment pin")
    pin.add_argument("--model", required=True, help="relative file inside /app/local-ai")
    pin.add_argument("--executable", required=True, help="relative file inside /app/local-ai")
    pin.add_argument("--profile", choices=PROFILES, default="qwen3-completion-chat")
    pin.add_argument("--context", type=int, default=4096)
    pin.add_argument("--threads", type=int)
    pin.add_argument("--gpu-layers", type=int, default=0)
    preflight = sub.add_parser("preflight", help="Verify pinned bytes, not inference")
    preflight.add_argument("--require-env", action="store_true")
    qualify = sub.add_parser("qualify", help="Execute real offline GGUF inference")
    qualify.add_argument("--max-output-tokens", type=int, default=32)
    args = parser.parse_args(argv)
    try:
        if args.action == "pin":
            receipt = pin_deployment(
                model=args.model, executable=args.executable,
                profile=args.profile, context=args.context,
                threads=args.threads, gpu_layers=args.gpu_layers,
            )
        elif args.action == "preflight":
            receipt = inspect_deployment(require_env=args.require_env)
        else:
            receipt = qualify_deployment(max_output_tokens=args.max_output_tokens)
    except (DockerLocalAIError, LocalModelDeploymentError, OSError, ValueError, TypeError):
        # Reject without reflecting host paths, secrets, or model prompts.
        print(json.dumps({
            "ok": False,
            "error": "Local Docker model admission or qualification failed; check private operator logs.",
        }), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
