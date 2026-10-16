"""Provision the pinned optional CPU chat model; never start inference or services.

Downloads require --download. Existing approved files can be supplied instead.
Only the canonical local deployment loader admits the resulting configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODEL = {
    "filename": "Qwen3-0.6B-Q8_0.gguf",
    "url": "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/23749fefcc72300e3a2ad315e1317431b06b590a/Qwen3-0.6B-Q8_0.gguf",
    "sha256": "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031",
    "bytes": 639_446_688,
    "license": "Apache-2.0",
}
RUNTIME = {
    "filename": "llama-b11429-bin-ubuntu-x64.tar.gz",
    "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-ubuntu-x64.tar.gz",
    "sha256": "f6d25dde8f51133143d1453da4fd5f73b145127177612a283bf7995957af3392",
    "bytes": 17_693_462,
    "license": "MIT",
}
EXECUTABLE_SHA256 = "7119bef261611b26f326f7c4da4dc3fdeb7bb28e2faf1ec392bda7b21215ef52"
SCHEMA = "skeleton.application.local_model_provisioning_receipt.v1"
MAX_EXTRACTED = 128 * 1024 * 1024
TARGET = "linux-x86_64-glibc"
DOWNLOAD_SECONDS = 1800
_DOWNLOAD_PROGRAM = r"""import hashlib,os,sys,time,urllib.request
url,expected_text,destination=sys.argv[1:]
expected=int(expected_text)
request=urllib.request.Request(url,headers={'User-Agent':'Skeleton-Local-Model-Installer/1.0','Accept-Encoding':'identity'})
with urllib.request.urlopen(request,timeout=60) as origin,open(destination,'xb') as target:
    if not origin.geturl().startswith('https://') or origin.status!=200: raise ValueError('HTTPS success required')
    length=origin.headers.get('content-length')
    if length is not None and int(length)!=expected: raise ValueError('artifact length differs')
    received=0
    while True:
        block=origin.read1(min(1024*1024,expected+1-received))
        if not block: break
        received+=len(block)
        if received>expected: raise ValueError('artifact exceeds pinned length')
        target.write(block)
    if received!=expected: raise ValueError('artifact is truncated')
    target.flush();os.fsync(target.fileno())
"""
PROFILE_ARGS = [
    "--conversation",
    "--single-turn",
    "--simple-io",
    "--no-perf",
    "--no-escape",
    "--color",
    "off",
    "--jinja",
    "--reasoning",
    "off",
]


def _profile_args():
    from skeleton.ai.runtime.inference.deployment import QWEN3_COMPLETION_CHAT_TEMPLATE

    return [*PROFILE_ARGS, "--chat-template", QWEN3_COMPLETION_CHAT_TEMPLATE]


def _sha(path: Path) -> str:
    value = hashlib.sha256()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MODEL["bytes"]:
            raise ValueError("Artifact is not a bounded regular file.")
        count = 0
        while block := stream.read(1024 * 1024):
            count += len(block)
            if count > before.st_size:
                raise ValueError("Artifact grew during hashing.")
            value.update(block)
        if count != before.st_size or _identity(before) != _identity(os.fstat(stream.fileno())):
            raise ValueError("Artifact changed during hashing.")
    return value.hexdigest()


def _identity(value):
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _copy_pinned(source: Path, destination: Path, recipe: dict) -> None:
    source_stat = source.lstat()
    if not stat.S_ISREG(source_stat.st_mode):
        raise ValueError("Artifact source must be a regular file without a symlink.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(source, flags)
    with os.fdopen(descriptor, "rb") as origin:
        before = os.fstat(origin.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != recipe["bytes"]
            or _identity(before) != _identity(source_stat)
        ):
            raise ValueError("Source must be an exact-size regular artifact.")
        copied, digest = 0, hashlib.sha256()
        with destination.open("xb") as target:
            while True:
                block = origin.read(min(1024 * 1024, recipe["bytes"] + 1 - copied))
                if not block:
                    break
                copied += len(block)
                if copied > recipe["bytes"]:
                    raise ValueError("Source grew beyond its pinned byte bound.")
                digest.update(block)
                target.write(block)
            if (
                copied != recipe["bytes"]
                or digest.hexdigest() != recipe["sha256"]
                or _identity(before) != _identity(os.fstat(origin.fileno()))
            ):
                raise ValueError("Source identity or exact artifact bytes changed during copy.")
            target.flush()
            os.fsync(target.fileno())


def _download_pinned(destination: Path, recipe: dict) -> None:
    names = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "CODEX_PROXY_CERT",
    }
    environment = {name: os.environ[name] for name in names if name in os.environ}
    environment.update(PATH=os.defpath, LANG="C.UTF-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            _DOWNLOAD_PROGRAM,
            recipe["url"],
            str(recipe["bytes"]),
            str(destination),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        close_fds=True,
    )
    try:
        if process.wait(timeout=DOWNLOAD_SECONDS) != 0:
            raise ValueError("Pinned artifact transfer failed.")
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Artifact transfer exceeded its absolute deadline.") from exc
    finally:
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        "Artifact download cleanup is not quiescent; destination remains incomplete."
                    ) from exc


def _verify(path: Path, recipe: dict) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Artifact must be an existing regular file, without a symlink.")
    if path.stat().st_size != recipe["bytes"] or _sha(path) != recipe["sha256"]:
        raise ValueError("Artifact bytes or SHA256 do not match the pinned recipe.")


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _acquire(destination: Path, recipe: dict, source: Path | None, *, download: bool) -> None:
    if source is not None:
        source = source.expanduser().absolute()
        _copy_pinned(source, destination, recipe)
    else:
        if not download:
            raise ValueError("Supply both existing artifacts, or explicitly request --download.")
        _download_pinned(destination, recipe)
    _verify(destination, recipe)


def _runtime_files(archive: Path, target: Path) -> list[dict]:
    """Resolve bounded archive aliases into regular files; never extract links."""
    target.mkdir(mode=0o755)
    target.chmod(0o755)
    with tarfile.open(archive, "r:gz") as bundle:
        members = {}
        declared_bytes = 0
        for member in bundle:
            if len(members) >= 512:
                raise ValueError("Runtime archive has too many members.")
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or len(name.parts) not in (1, 2):
                raise ValueError("Runtime archive path is outside its fixed root.")
            if name.parts[0] != "llama-b11429" or member.name in members:
                raise ValueError("Runtime archive identity or member uniqueness differs.")
            if member.size < 0 or member.size > MAX_EXTRACTED:
                raise ValueError("Runtime archive member size exceeds its bound.")
            declared_bytes += member.size
            if declared_bytes > MAX_EXTRACTED:
                raise ValueError("Runtime archive total declared size exceeds its bound.")
            members[member.name] = member
        selected = [
            name
            for name in members
            if len(PurePosixPath(name).parts) == 2
            and (
                PurePosixPath(name).name in {"llama-completion", "LICENSE"}
                or (PurePosixPath(name).name.startswith("lib") and ".so" in PurePosixPath(name).name)
            )
        ]
        if not {"llama-b11429/llama-completion", "llama-b11429/LICENSE"}.issubset(selected):
            raise ValueError("Runtime archive is missing its executable or license.")
        records, total = [], 0
        for name in sorted(selected):
            member, visited = members[name], set()
            while member.issym():
                if member.name in visited or len(visited) >= 8:
                    raise ValueError("Runtime archive alias is cyclic.")
                visited.add(member.name)
                alias = PurePosixPath(member.linkname)
                if alias.is_absolute() or len(alias.parts) != 1 or alias.name in {".", ".."}:
                    raise ValueError("Runtime alias escapes its fixed library directory.")
                member = members.get("llama-b11429/" + alias.name)
                if member is None:
                    raise ValueError("Runtime archive alias has no target.")
            if not member.isfile() or not 0 < member.size <= 32 * 1024 * 1024:
                raise ValueError("Runtime archive contains an unsupported member.")
            total += member.size
            if total > MAX_EXTRACTED:
                raise ValueError("Expanded runtime exceeds its size bound.")
            output = target / PurePosixPath(name).name
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError("Runtime archive member could not be opened.")
            with source, output.open("xb") as stream:
                shutil.copyfileobj(source, stream, 1024 * 1024)
            if output.stat().st_size != member.size:
                raise ValueError("Runtime archive member was truncated.")
            output.chmod(0o444 if output.name == "LICENSE" else 0o555)
            records.append({"path": "runtime/" + output.name, "bytes": member.size, "sha256": _sha(output)})
    if _sha(target / "llama-completion") != EXECUTABLE_SHA256:
        raise ValueError("Runtime executable does not match its pinned digest.")
    return records


def _existing(target: Path, *, threads: int, context_size: int = 8192) -> dict:
    from skeleton.ai.runtime.inference.deployment import LocalModelDeployment

    if target.is_symlink() or (target / ".incomplete").exists():
        raise ValueError("Destination is incomplete or symlinked; choose a new directory.")
    receipt_path = target / "provisioning.json"
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > 128 * 1024:
        raise ValueError("Existing directory has no bounded provisioning receipt.")
    receipt = json.loads(receipt_path.read_text())
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    identity = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if receipt.get("schema_version") != SCHEMA or receipt.get("receipt_digest") != identity:
        raise ValueError("Existing provisioning receipt identity differs.")
    if receipt.get("model") != MODEL or receipt.get("runtime") != RUNTIME:
        raise ValueError("Existing provisioning recipe differs.")
    if receipt.get("runtime_platform") != TARGET:
        raise ValueError("Existing target runtime differs.")
    records = receipt.get("files")
    if not isinstance(records, list) or not 4 <= len(records) <= 512:
        raise ValueError("Existing provisioning file list is invalid.")
    paths, total = set(), 0
    for record in records:
        if type(record.get("bytes")) is not int or not 0 < record["bytes"] <= MODEL["bytes"]:
            raise ValueError("Existing provisioning file bound is invalid.")
        total += record["bytes"]
        if total > MODEL["bytes"] + MAX_EXTRACTED + 128 * 1024:
            raise ValueError("Existing provisioning total file bound is invalid.")
        relative = PurePosixPath(record["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) > 2
            or str(relative) in paths
        ):
            raise ValueError("Provisioning file path is invalid or duplicated.")
        paths.add(str(relative))
        path = target.joinpath(*relative.parts)
        if path.resolve() != path.absolute():
            raise ValueError("Provisioning path contains a symlink.")
        _verify(path, record)
    required = {MODEL["filename"], "runtime/llama-completion", "runtime/LICENSE", "deployment.json"}
    if not required.issubset(paths):
        raise ValueError("Provisioning receipt omits a required artifact.")
    _verify(target / MODEL["filename"], MODEL)
    if _sha(target / "runtime/llama-completion") != EXECUTABLE_SHA256:
        raise ValueError("Existing runtime executable identity differs.")
    deployment = LocalModelDeployment.load(target / "deployment.json")
    if deployment.manifest_digest != receipt.get("deployment_digest"):
        raise ValueError("Existing deployment identity differs.")
    if deployment.threads != threads:
        raise ValueError("Existing thread configuration conflicts; choose a new directory.")
    if (
        deployment.model_id != "Qwen3-0.6B-Q8_0"
        or deployment.context_size != context_size
        or deployment.batch_size != 512
        or deployment.gpu_layers != 0
        or deployment.timeout_seconds != 600
        or deployment.temperature != 0.0
        or deployment.extra_args != tuple(_profile_args())
        or deployment.output_framing != "llama_completion_eog"
    ):
        raise ValueError("Existing deployment profile differs from the pinned installer recipe.")
    return receipt


def _platform_diagnostic(args):
    if args.target != TARGET:
        raise ValueError("Only the pinned linux-x86_64-glibc target is supported.")
    system, machine, libc = platform.system(), platform.machine().lower(), platform.libc_ver()[0]
    compatible = system == "Linux" and machine in {"x86_64", "amd64"} and libc == "glibc"
    if not compatible and not args.prepare_for_container:
        raise ValueError(
            "This runtime requires Linux x86_64 glibc; use explicit container preparation on another host."
        )
    return {
        "target": TARGET,
        "host_system": system,
        "host_machine": machine,
        "host_libc": libc or "unknown",
        "host_native_compatible": compatible,
        "preparation_mode": "container" if args.prepare_for_container else "native",
        "native_execution_verified": False,
    }


def provision(args) -> dict:
    from skeleton.ai.runtime.inference.deployment import SCHEMA as DEPLOYMENT_SCHEMA
    from skeleton.ai.runtime.inference.deployment import LocalModelDeployment

    if type(args.threads) is not int or not 1 <= args.threads <= 8:
        raise ValueError("Threads must be between one and eight.")
    context_size = getattr(args, "context_size", 8192)
    if type(context_size) is not int or context_size not in {4096, 8192, 12288, 16384}:
        raise ValueError("Context size must be 4096, 8192, 12288 or 16384 tokens.")
    platform_diagnostic = _platform_diagnostic(args)
    target = args.output.expanduser().absolute()
    existing_empty = False
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_dir() or target.resolve() != target:
            raise ValueError("Destination must be a nonsymlink artifact directory.")
        if any(target.iterdir()):
            receipt = _existing(target, threads=args.threads, context_size=context_size)
            return {
                "status": "verified_existing",
                "receipt_digest": receipt["receipt_digest"],
                "destination": str(target),
                "platform": platform_diagnostic,
                "threads": args.threads,
                "context_size": context_size,
            }
        ownership = target.stat()
        if (
            not hasattr(os, "geteuid")
            or ownership.st_uid != os.geteuid()
            or stat.S_IMODE(ownership.st_mode) & 0o022
        ):
            raise ValueError(
                "An existing empty directory must be operator-owned and not writable by other users."
            )
        existing_empty = True
    if not args.download and (args.model is None or args.runtime_archive is None):
        raise ValueError("Supply both pinned local artifacts or explicitly request --download.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.resolve() != target.parent:
        raise ValueError("Destination parent must not contain symlinks.")
    if shutil.disk_usage(target.parent).free < 2 * 1024**3:
        raise ValueError("Provisioning requires at least two GiB free disk space.")
    if not existing_empty:
        target.mkdir(mode=0o755)
    marker = target / ".incomplete"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("Not admitted. Do not activate this directory.\n")
        stream.flush()
        os.fsync(stream.fileno())
    if any(path.name != ".incomplete" for path in target.iterdir()):
        raise ValueError("Destination changed while claiming the empty artifact directory.")
    target.chmod(0o755)
    model = target / MODEL["filename"]
    archive = target / RUNTIME["filename"]
    _acquire(model, MODEL, args.model, download=args.download)
    _acquire(archive, RUNTIME, args.runtime_archive, download=args.download)
    files = _runtime_files(archive, target / "runtime")
    model.chmod(0o444)
    archive.unlink()
    manifest = {
        "schema_version": DEPLOYMENT_SCHEMA,
        "runtime_kind": "llama.cpp-cli",
        "model_id": "Qwen3-0.6B-Q8_0",
        "executable_path": "runtime/llama-completion",
        "executable_sha256": EXECUTABLE_SHA256,
        "model_path": MODEL["filename"],
        "model_sha256": MODEL["sha256"],
        "config": {
            "context_size": context_size,
            "threads": args.threads,
            "batch_size": 512,
            "gpu_layers": 0,
            "timeout_seconds": 600,
            "temperature": 0.0,
            "extra_args": _profile_args(),
            "output_framing": "llama_completion_eog",
        },
    }
    candidate = target / ".deployment-candidate.json"
    _write_json(candidate, manifest)
    admitted = LocalModelDeployment.load(candidate)
    for name in (MODEL["filename"], "deployment.json"):
        path = model if name == MODEL["filename"] else candidate
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": _sha(path)})
    receipt = {
        "schema_version": SCHEMA,
        "model": MODEL,
        "runtime": RUNTIME,
        "runtime_platform": TARGET,
        "preparation": platform_diagnostic,
        "files": sorted(files, key=lambda item: item["path"]),
        "deployment_digest": admitted.manifest_digest,
        "inference_executed": False,
        "production_promotion_authorized": False,
    }
    receipt["receipt_digest"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    _write_json(target / "provisioning.json", receipt)
    (target / "provisioning.json").chmod(0o444)
    candidate.chmod(0o444)
    os.link(candidate, target / "deployment.json")
    candidate.unlink()
    marker.unlink()
    return {
        "status": "provisioned",
        "receipt_digest": receipt["receipt_digest"],
        "destination": str(target),
        "model_bytes": MODEL["bytes"],
        "runtime_files": len(files) - 2,
        "platform": platform_diagnostic,
        "threads": args.threads,
        "context_size": context_size,
        "activation": {
            "AI_PROVIDER": "local",
            "AI_LOCAL_MODEL_PATH": "",
            "AI_LOCAL_DEPLOYMENT_PATH": "/app/local-ai/deployment.json",
        },
        "inference_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="new operator artifact directory, e.g. ./data/local-ai"
    )
    parser.add_argument("--target", required=True, choices=(TARGET,), help="explicit pinned runtime target")
    parser.add_argument(
        "--prepare-for-container",
        action="store_true",
        help="prepare Linux x86_64 artifacts on another host; target container must support this runtime",
    )
    parser.add_argument(
        "--download", action="store_true", help="explicitly download the fixed ~657 MB public artifacts"
    )
    parser.add_argument("--model", type=Path, help="existing exact pinned Qwen GGUF instead of downloading")
    parser.add_argument(
        "--runtime-archive", type=Path, help="existing exact pinned Ubuntu x64 release archive"
    )
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument(
        "--context-size",
        type=int,
        choices=(4096, 8192, 12288, 16384),
        default=8192,
        help="requested context; use 12288 for the original studio workflow when capacity permits",
    )
    args = parser.parse_args()
    try:
        result = provision(args)
    except (OSError, ValueError, tarfile.TarError, RuntimeError, KeyError, TypeError):
        # Underlying transport exceptions may contain proxy URLs and credentials.
        print(
            "Local AI provisioning failed. Verify the pinned artifacts, free space and trusted proxy/CA configuration. An incomplete destination is never activated; use a new directory after correcting the issue.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
