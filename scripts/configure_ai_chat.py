#!/usr/bin/env python3
"""Write private operator configuration for the existing local Compose stack.

This command never starts a service, probes a provider, loads model weights or
prints a credential. Use an existing environment variable to supply a hosted
key, or bind an existing local artifact through the generated Compose override.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shlex
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_LOCAL_TARGET = "/app/configured-local-ai"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUNTIME_LIBRARY = re.compile(r"lib[A-Za-z0-9_.+\-]+\.so(?:\.[A-Za-z0-9_.+\-]+)?\Z")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_TENANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,511}\Z")
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")
_PLACEHOLDER_KEYS = {"sk-your-key-here", "your-key-here", "your_api_key", "changeme", "change-me"}
_MONGO_KEYS = (
    "MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD", "MONGO_INITDB_DATABASE",
    "MONGO_URL", "SKL_MONGO_URI",
)


class ConfigurationError(ValueError):
    """A configuration cannot be written safely; messages contain no values."""


def _safe_value(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ConfigurationError(field + " contains an unsupported value")
    # Compose single-quoted dotenv values prevent variable interpolation. Keep
    # this literal representation unambiguous rather than silently changing a
    # credential through quote/backslash escaping.
    if "'" in value or "\\" in value:
        raise ConfigurationError(field + " cannot be represented safely in this environment file")
    return value


def _dotenv_literal(value: str, field: str) -> str:
    """Use the canonical setup literal format for quotes, slashes and dollars."""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ConfigurationError(field + " contains an unsupported environment value")
    try:
        literal = json.dumps(value, ensure_ascii=False).replace("$", "$$")
        literal.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ConfigurationError(field + " must be valid Unicode") from exc
    return literal


def _checked_path(path: Path, *, output: bool = False) -> Path:
    result = path.expanduser().absolute()
    if any(ord(character) < 32 or ord(character) == 127 for character in str(result)):
        raise ConfigurationError("file path contains control characters")
    for component in reversed((result, *result.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if component == result and output:
                continue
            raise ConfigurationError("output parent or local artifact does not exist") from None
        if stat.S_ISLNK(info.st_mode):
            raise ConfigurationError("symlink paths are not supported")
        if component != result and not stat.S_ISDIR(info.st_mode):
            raise ConfigurationError("file parent must be a directory")
        if component == result and not stat.S_ISREG(info.st_mode):
            raise ConfigurationError("configuration output and local artifact must be regular files")
    return result


def _public_host(value: str) -> str:
    candidate = value.strip()
    if candidate != value or not candidate or len(candidate) > 253:
        raise ConfigurationError("public host must be a normalized hostname or IP address")
    _safe_value(candidate, "public host")
    unbracketed = candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    try:
        address = ipaddress.ip_address(unbracketed)
    except ValueError:
        if _HOST.fullmatch(candidate) is None or ".." in candidate:
            raise ConfigurationError(
                "public host must not include a URL, port, credentials or path"
            ) from None
        return candidate
    if address.version == 6 and getattr(address, "scope_id", None) is not None:
        raise ConfigurationError("public host must not include a scoped IPv6 interface")
    return "[" + str(address) + "]" if address.version == 6 else str(address)


def _port(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 65535:
        raise ConfigurationError("service ports must be in [1, 65535]")
    return value


def _private_write(path: Path, content: bytes, *, force: bool, mode: int = 0o600) -> None:
    """Install a complete file; only generated non-secret manifests use 0644."""
    if mode not in {0o600, 0o644}:
        raise ConfigurationError("configuration output mode is invalid")
    target = _checked_path(path, output=True)
    prior = None
    try:
        prior = target.lstat()
    except FileNotFoundError:
        pass
    if prior is not None and not force:
        raise ConfigurationError("an output already exists; use --force only for intentional replacement")
    parent_before = target.parent.stat()
    # Existing Git and Docker ignore rules exclude .env.* even if a process
    # dies before cleanup; a private temporary must never enter a build layer.
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.chat-tmp-", dir=target.parent)
    temporary = Path(temporary_name)
    installed = False
    temporary_identity = temporary.stat()
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), mode)
            else:
                os.chmod(temporary, mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        parent_after = target.parent.lstat()
        if stat.S_ISLNK(parent_after.st_mode) or (parent_before.st_dev, parent_before.st_ino) != (
            parent_after.st_dev,
            parent_after.st_ino,
        ):
            raise ConfigurationError("configuration output directory changed")
        if force and prior is not None:
            current = target.lstat()
            if (
                stat.S_ISLNK(current.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns, current.st_size)
                != (prior.st_dev, prior.st_ino, prior.st_mtime_ns, prior.st_ctime_ns, prior.st_size)
            ):
                raise ConfigurationError("configuration output changed before replacement")
            os.replace(temporary, target)
            installed = True
        else:
            # Hard-link creation is atomic and refuses an existing destination.
            # The temporary already contains the complete private bytes.
            os.link(temporary, target, follow_symlinks=False)
            installed = True
        if os.name != "nt":
            directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError as exc:
        if installed and prior is None:
            try:
                current = target.lstat()
                if (current.st_dev, current.st_ino) == (temporary_identity.st_dev, temporary_identity.st_ino):
                    target.unlink()
            except OSError:
                pass
        raise ConfigurationError("private configuration output could not be installed") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError("local model metadata contains duplicate JSON keys")
        result[key] = value
    return result


def _manifest_constant(_value: str) -> None:
    raise ConfigurationError("local model metadata contains non-finite JSON")


def _read_manifest(path: Path) -> tuple[dict, bytes]:
    """Read only bounded configuration; never restore a native model graph."""
    path = _checked_path(path)
    info = path.stat()
    if not 1 <= info.st_size <= _MAX_MANIFEST_BYTES:
        raise ConfigurationError("local model metadata exceeds its byte bound")
    with path.open("rb") as stream:
        raw = stream.read(_MAX_MANIFEST_BYTES + 1)
    current = path.stat()
    if len(raw) != info.st_size or len(raw) > _MAX_MANIFEST_BYTES or (
        info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    ) != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns):
        raise ConfigurationError("local model metadata changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_manifest_object, parse_constant=_manifest_constant)
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise ConfigurationError("local model metadata is not finite UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("local model metadata must be a JSON object")
    return value, raw


def _source_path(base: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConfigurationError("local model source path must be normalized text")
    path = Path(value).expanduser()
    return _checked_path(path if path.is_absolute() else base / path)


def _local_model_name(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise ConfigurationError("local model names must be normalized non-empty text")
    try:
        if len(value.encode("utf-8", errors="strict")) > 256:
            raise ConfigurationError("local model names exceed their 256-byte bound")
    except UnicodeEncodeError as exc:
        raise ConfigurationError("local model names must be valid Unicode") from exc
    return value


def _pinned_file(path: Path, expected: object, *, maximum: int) -> int:
    if not isinstance(expected, str) or _SHA256.fullmatch(expected) is None:
        raise ConfigurationError("local model source digest must be lowercase SHA-256")
    info = path.stat()
    if not 1 <= info.st_size <= maximum:
        raise ConfigurationError("local model source exceeds its declared byte budget")
    value, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while True:
            block = stream.read(min(1024 * 1024, info.st_size + 1 - count))
            if not block:
                break
            count += len(block)
            if count > info.st_size:
                raise ConfigurationError("local model source grew while hashing")
            value.update(block)
    current = path.stat()
    if count != info.st_size or value.hexdigest() != expected or (
        info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    ) != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns):
        raise ConfigurationError("local model source differs from its declared digest pin")
    return count


def _local_binding(source: Path, target: str) -> dict:
    # Compose interpolates dollar signs even inside a JSON-encoded override.
    # Escaping preserves literal host filenames without reading environment.
    return {
        "type": "bind", "source": str(source).replace("$", "$$"), "target": target.replace("$", "$$"),
        "read_only": True, "bind": {"create_host_path": False},
    }


def _prepared_local_sources(options: dict, *, force: bool, dry_run: bool) -> None:
    """Prepare portable manifests and explicit file bindings without execution."""
    options.update(
        local_manifests=[], local_bindings=[], local_reader_paths=[],
        local_executable_paths=[], local_source_paths=[], local_platform=None,
    )
    if options["deployment"] is None and options["catalog"] is None:
        return
    output_prefix = str(options["env_file"])
    referenced: dict[Path, int] = {}
    target_counts = 0
    platforms: set[str] = set()

    def add_source(source: Path, target: str, *, activation_source: bool = True) -> None:
        options["local_bindings"].append(_local_binding(source, target))
        options["local_reader_paths"].append(source)
        if activation_source:
            referenced[source] = source.stat().st_size

    def prepare_deployment(source: Path, *, maximum: int) -> tuple[Path, str, bytes]:
        nonlocal target_counts
        options["local_source_paths"].append(source)
        payload, _raw = _read_manifest(source)
        required = {"schema_version", "runtime_kind", "model_id", "executable_path", "executable_sha256", "model_path", "model_sha256"}
        if not required <= set(payload) or set(payload) - required - {"config"} or (
            payload.get("schema_version") != "skeleton.local_model.deployment.v1"
            or payload.get("runtime_kind") != "llama.cpp-cli"
            or not isinstance(payload.get("config", {}), dict)
        ):
            raise ConfigurationError("unsupported local deployment manifest")
        if not isinstance(payload["model_id"], str):
            raise ConfigurationError("local deployment requires a model name")
        model_name = _local_model_name(payload["model_id"].strip())
        model = _source_path(source.parent, payload["model_path"])
        executable = _source_path(source.parent, payload["executable_path"])
        _pinned_file(model, payload["model_sha256"], maximum=maximum)
        _pinned_file(executable, payload["executable_sha256"], maximum=min(maximum, 128 * 1024 * 1024))
        with executable.open("rb") as stream:
            header = stream.read(20)
        if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] != 2 or header[5] not in {1, 2} or header[6] != 1:
            raise ConfigurationError("Docker local deployments require a Linux ELF runtime, not a host-specific executable")
        machine = int.from_bytes(header[18:20], "little" if header[5] == 1 else "big")
        platform_name = {62: "linux/amd64", 183: "linux/arm64"}.get(machine)
        if platform_name is None:
            raise ConfigurationError("local runtime architecture is unsupported by the configured engine image")
        platforms.add(platform_name)
        if os.name != "nt" and not os.access(executable, os.X_OK):
            raise ConfigurationError("local runtime executable needs an existing execute grant")
        index = target_counts
        target_counts += 1
        runtime_target = _LOCAL_TARGET + f"/runtime-{index}"
        model_target = _LOCAL_TARGET + f"/model-{index}.gguf"
        executable_target = runtime_target + "/" + executable.name
        add_source(model, model_target)
        add_source(executable, executable_target)
        options["local_executable_paths"].append(executable)
        # The pinned installer stores shared libraries beside llama-completion.
        # Bind only bounded library files, including resolved alias filenames;
        # do not expose the whole operator directory or copy executables.
        libraries = []
        for entry_count, candidate in enumerate(executable.parent.iterdir(), 1):
            if entry_count > 4096:
                raise ConfigurationError("local runtime directory exceeds its metadata enumeration bound")
            if _RUNTIME_LIBRARY.fullmatch(candidate.name):
                libraries.append(candidate)
                if len(libraries) > 128:
                    raise ConfigurationError("local runtime directory contains too many shared libraries")
        library_bytes = 0
        for candidate in sorted(libraries):
            try:
                resolved = candidate.resolve(strict=True) if candidate.is_symlink() else candidate
            except (OSError, RuntimeError) as exc:
                raise ConfigurationError("local runtime library aliases could not be resolved safely") from exc
            library = _checked_path(resolved)
            library_bytes += library.stat().st_size
            if library_bytes > 128 * 1024 * 1024:
                raise ConfigurationError("local runtime shared libraries exceed the container binding budget")
            add_source(library, runtime_target + "/" + candidate.name, activation_source=False)
        prepared = dict(payload)
        prepared["model_id"] = model_name
        prepared["model_path"] = model_target
        prepared["executable_path"] = executable_target
        raw = (json.dumps(prepared, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise ConfigurationError("prepared local deployment exceeds the metadata byte bound")
        destination = _checked_path(Path(output_prefix + f".local-deployment-{index}.json"), output=True)
        target = _LOCAL_TARGET + f"/deployment-{index}.json"
        options["local_manifests"].append((destination, raw))
        options["local_bindings"].append(_local_binding(destination, target))
        return destination, target, raw

    if options["deployment"] is not None:
        _, target, _ = prepare_deployment(options["deployment"], maximum=1024**4)
        options["local_container_path"] = target
    else:
        source = options["catalog"]
        payload, _source_raw = _read_manifest(source)
        required = {"schema_version", "primary_model_id", "max_total_artifact_bytes", "models"}
        if not required <= set(payload) or set(payload) - required - {"verifier_model_id"} or payload.get("schema_version") != "skeleton.local_model.catalog.v1":
            raise ConfigurationError("unsupported local model catalog")
        models, budget = payload["models"], payload["max_total_artifact_bytes"]
        if not isinstance(models, list) or not 1 <= len(models) <= 8 or type(budget) is not int or not 1 <= budget <= 1024**4:
            raise ConfigurationError("local model catalog requires 1–8 models and a bounded integer byte budget")
        primary = _local_model_name(payload["primary_model_id"])
        verifier = _local_model_name(payload["verifier_model_id"]) if "verifier_model_id" in payload else None
        prepared_models, names = [], set()
        for index, row in enumerate(models):
            if not isinstance(row, dict) or set(row) != {"model_id", "kind", "path", "sha256"}:
                raise ConfigurationError("local catalog entries require exact model, kind, path and digest fields")
            name = _local_model_name(row["model_id"])
            if name in names:
                raise ConfigurationError("local catalog model names must be bounded, normalized and unique")
            names.add(name)
            entry_source = _source_path(source.parent, row["path"])
            _pinned_file(entry_source, row["sha256"], maximum=_MAX_ARTIFACT_BYTES if row["kind"] == "artifact" else _MAX_MANIFEST_BYTES)
            if row["kind"] == "deployment":
                _, target, raw = prepare_deployment(entry_source, maximum=budget)
                digest = hashlib.sha256(raw).hexdigest()
            elif row["kind"] == "artifact":
                target = _LOCAL_TARGET + f"/artifact-{index}.json"
                add_source(entry_source, target)
                digest = row["sha256"]
            else:
                raise ConfigurationError("local catalog kind must be artifact or deployment")
            prepared_models.append({**row, "path": target, "sha256": digest})
        if primary not in names or (verifier is not None and (verifier not in names or verifier == primary)):
            raise ConfigurationError("local catalog primary and verifier must name distinct configured entries")
        # Match the canonical activation budget: model files, executables and
        # prepared manifests. Neighbor libraries have a separate 128 MiB cap.
        prepared_bytes = sum(size for size in referenced.values()) + sum(len(raw) for _, raw in options["local_manifests"])
        if prepared_bytes > budget:
            raise ConfigurationError("portable catalog bindings exceed the declared artifact byte budget")
        raw = (json.dumps({**payload, "models": prepared_models}, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if len(raw) > _MAX_MANIFEST_BYTES:
            raise ConfigurationError("prepared local catalog exceeds its metadata byte bound")
        destination = _checked_path(Path(output_prefix + ".local-catalog.json"), output=True)
        target = _LOCAL_TARGET + "/catalog.json"
        options["local_manifests"].append((destination, raw))
        options["local_bindings"].append(_local_binding(destination, target))
        options["local_container_path"] = target
    if len(platforms) > 1:
        raise ConfigurationError("one engine catalog cannot mix different Linux runtime architectures")
    options["local_platform"] = next(iter(platforms), None)
    for path, _raw in options["local_manifests"]:
        if path.exists() and not force and not dry_run:
            raise ConfigurationError("a prepared local manifest already exists; intentional replacement requires --force")


def _existing_private_environment(env_file: Path) -> dict[str, str]:
    """Read the selected prior configuration without changing its identity."""
    if not env_file.exists():
        return {}
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from skeleton.app.setup_runtime import _parse_env

    with env_file.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(256 * 1024 + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > 256 * 1024:
        raise ConfigurationError("existing private environment exceeds its bounded configuration size")
    if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (
        after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size,
    ):
        raise ConfigurationError("existing private environment changed while reading")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ConfigurationError("existing private environment is not valid UTF-8") from exc
    keys = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError("existing private environment contains unsupported assignments")
        name = line.split("=", 1)[0].strip()
        if _VARIABLE.fullmatch(name) is None or name in keys:
            raise ConfigurationError("existing private environment contains invalid or duplicate assignments")
        keys.add(name)
    return _parse_env(text)


def _options(args) -> dict:
    local_deployment = getattr(args, "local_deployment", None)
    local_catalog = getattr(args, "local_catalog", None)
    admin = None
    if getattr(args, "admin_email", None) is not None or getattr(args, "admin_password_file", None) is not None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from skeleton.app.setup_runtime import _operator_admin

        try:
            admin = _operator_admin(
                getattr(args, "admin_email", None),
                None if getattr(args, "admin_password_file", None) is None else Path(args.admin_password_file),
            )
        except (OSError, ValueError) as exc:
            raise ConfigurationError("admin bootstrap requires a valid email and a private password file meeting the canonical password policy") from exc
    env_file = _checked_path(Path(args.env_file), output=True)
    if not (env_file.name == ".env" or env_file.name.startswith(".env.")) or env_file.name.endswith(
        ".example"
    ):
        raise ConfigurationError("choose a private .env or .env.* file excluded from Git and Docker builds")
    override = Path(str(env_file) + ".compose.json")
    instructions = Path(str(env_file) + ".README.md")
    for path in (env_file, override, instructions):
        _checked_path(path, output=True)
        if path.exists() and not args.force and not args.dry_run:
            raise ConfigurationError("an output already exists; intentional replacement requires --force")
    prior = _existing_private_environment(env_file)
    host = _public_host(args.public_host)
    ports = [
        _port(value) for value in (args.backend_port, args.skeleton_port, args.frontend_port, args.mongo_port)
    ]
    if len(set(ports)) != len(ports):
        raise ConfigurationError("backend, engine, frontend and MongoDB host ports must differ")
    tenants = tuple(dict.fromkeys(args.tenant or ("default",)))
    if len(tenants) > 64 or any(_TENANT.fullmatch(tenant) is None for tenant in tenants):
        raise ConfigurationError(
            "tenants must be bounded explicit identities without CSV separators or wildcards"
        )
    model = "" if args.model is None else args.model
    if model and (model != model.strip() or len(model) > 256):
        raise ConfigurationError("model must be a normalized bounded identity")
    _safe_value(model, "model")
    key = ""
    artifact = deployment = catalog = None
    if args.provider == "local":
        selections = (args.local_artifact, local_deployment, local_catalog)
        if sum(value is not None for value in selections) != 1 or args.model is not None or args.openai_key_env is not None:
            raise ConfigurationError(
                "local mode requires exactly one artifact, deployment or catalog and does not accept hosted key or model overrides"
            )
        if args.local_artifact is not None:
            artifact = _checked_path(Path(args.local_artifact))
            if not 1 <= artifact.stat().st_size <= _MAX_ARTIFACT_BYTES:
                raise ConfigurationError("local artifact violates byte bounds")
        if local_deployment is not None:
            deployment = _checked_path(Path(local_deployment))
        if local_catalog is not None:
            catalog = _checked_path(Path(local_catalog))
    else:
        if any(value is not None for value in (args.local_artifact, local_deployment, local_catalog)):
            raise ConfigurationError("hosted mode does not accept local model inputs")
        variable = args.openai_key_env or "OPENAI_API_KEY"
        if _VARIABLE.fullmatch(variable) is None:
            raise ConfigurationError("hosted key variable name is invalid")
        key = os.environ.get(variable, "")
        if args.openai_key_env is None and variable not in os.environ:
            key = prior.get("OPENAI_API_KEY", "")
        if args.openai_key_env is not None and not key:
            raise ConfigurationError("the selected hosted key environment variable is empty")
        _safe_value(key, "hosted key")
        if key.strip().lower() in _PLACEHOLDER_KEYS:
            raise ConfigurationError("a documented placeholder cannot configure hosted credentials")
        inherited = os.environ.get("OPENAI_API_KEY")
        if inherited is not None and inherited != key:
            raise ConfigurationError("exported OPENAI_API_KEY conflicts with the explicitly selected key source")
    options = {
        "env_file": env_file,
        "override": override,
        "instructions": instructions,
        "host": host,
        "backend_port": ports[0],
        "skeleton_port": ports[1],
        "frontend_port": ports[2],
        "mongo_port": ports[3],
        "tenants": tenants,
        "model": model,
        "key": key,
        "artifact": artifact,
        "deployment": deployment,
        "catalog": catalog,
        "provider": args.provider,
        "admin": admin,
        "prior_environment": prior,
    }
    _prepared_local_sources(options, force=args.force, dry_run=args.dry_run)
    inputs = {path for path in (
        artifact, deployment, catalog, *options["local_reader_paths"], *options["local_source_paths"],
    ) if path is not None}
    outputs = (env_file, override, instructions, *(path for path, _raw in options["local_manifests"]))
    for source in inputs:
        if any(source == output or (output.exists() and source.samefile(output)) for output in outputs):
            raise ConfigurationError("operator model inputs and generated configuration outputs must be distinct")
    return options


def _persistent_mongo_credentials(prior: dict[str, str]) -> tuple[dict[str, str], bool]:
    """Keep the attached database identity as one complete, consistent group."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from skeleton.app.setup_runtime import _is_placeholder

    existing = {name: prior[name] for name in _MONGO_KEYS if name in prior}
    inherited = {name: os.environ[name] for name in _MONGO_KEYS if name in os.environ}
    if existing and len(existing) != len(_MONGO_KEYS):
        raise ConfigurationError("existing MongoDB credentials are incomplete; repair them explicitly before replacement")
    if existing:
        if any(value != existing[name] for name, value in inherited.items()):
            raise ConfigurationError("exported MongoDB credentials conflict with the selected private environment")
        values = existing
    elif inherited:
        if len(inherited) != len(_MONGO_KEYS):
            raise ConfigurationError("exported MongoDB credentials must form a complete matching configuration")
        values = inherited
    else:
        password = secrets.token_urlsafe(48)
        auth = "chat_admin:" + quote(password, safe="") + "@mongo:27017/"
        return {
            "MONGO_INITDB_ROOT_USERNAME": "chat_admin",
            "MONGO_INITDB_ROOT_PASSWORD": password,
            "MONGO_INITDB_DATABASE": "tutolage",
            "MONGO_URL": "mongodb://" + auth + "tutolage?authSource=admin",
            "SKL_MONGO_URI": "mongodb://" + auth + "skeleton?authSource=admin",
        }, True
    for name, value in values.items():
        _dotenv_literal(value, name)
        if not value or _is_placeholder(value):
            raise ConfigurationError("existing MongoDB credentials require a separate intentional repair")
    database = values["MONGO_INITDB_DATABASE"]
    if len(database.encode("utf-8")) > 63 or any(char in database for char in '/\\. "$*<>:|?'):
        raise ConfigurationError("existing MongoDB application database is invalid")
    endpoints = []
    for name, expected_database in (("MONGO_URL", database), ("SKL_MONGO_URI", "skeleton")):
        try:
            value = values[name]
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"mongodb", "mongodb+srv"}
                or parsed.fragment or parsed.netloc.count("@") != 1
                or not parsed.hostname or parsed.username is None or parsed.password is None
                or re.search(r"%(?![0-9a-fA-F]{2})", value)
                or any(char.isspace() or char in "\\$" for char in parsed.netloc.rsplit("@", 1)[1])
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
                or (parsed.scheme == "mongodb+srv" and parsed.port is not None)
            ):
                raise ValueError("unsupported MongoDB URI")
            query = parse_qs(parsed.query, strict_parsing=True, max_num_fields=64)
            if (
                unquote(parsed.username, errors="strict") != values["MONGO_INITDB_ROOT_USERNAME"]
                or unquote(parsed.password, errors="strict") != values["MONGO_INITDB_ROOT_PASSWORD"]
                or unquote(parsed.path, errors="strict") != "/" + expected_database
                or query.get("authSource") != ["admin"]
            ):
                raise ValueError("inconsistent MongoDB identity")
            endpoints.append((parsed.scheme, parsed.hostname.lower(), parsed.port or 27017))
        except (ValueError, UnicodeError) as exc:
            raise ConfigurationError("existing MongoDB URLs must match the preserved root credentials, databases and admin authentication source") from exc
    if endpoints[0] != endpoints[1]:
        raise ConfigurationError("existing MongoDB application and engine URLs must address the same database service")
    return values, False


def _persistent_studio_keys(options: dict) -> dict[str, str]:
    """Preserve store, session, service and artifact identity during rewrites."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from skeleton.app.setup_runtime import _is_placeholder, _operator_admin_values

    prior = options.get("prior_environment")
    if prior is None:
        prior = _existing_private_environment(options["env_file"])
    result, mongo_generated = _persistent_mongo_credentials(prior)
    options["database_credentials_generated"] = mongo_generated
    generated = []
    preserved = list(_MONGO_KEYS) if not mongo_generated else []
    for name in (
        "SKELETON_MASTER_SECRET", "GF_SEAL_SECRET", "GF_KEYHOLDER_SEED",
        "JWT_SECRET", "GAMEFORGE_JWT_SECRET", "SKL_ENGINE_SERVICE_TOKEN",
    ):
        existing = prior.get(name)
        inherited = os.environ.get(name)
        if existing is not None and inherited is not None and inherited != existing:
            raise ConfigurationError("exported persistent studio keys conflict with the selected private environment")
        value = existing if existing is not None else inherited
        if value is not None:
            if _is_placeholder(value):
                raise ConfigurationError("existing persistent credentials require a separate intentional repair")
            if name == "GF_KEYHOLDER_SEED":
                if len(value) != 64 or any(character not in "0123456789abcdefABCDEF" for character in value):
                    raise ConfigurationError("existing studio signing seed requires a separate intentional repair")
            elif not 32 <= len(value) <= 4096 or value != value.strip():
                raise ConfigurationError("existing persistent studio key requires a separate intentional repair")
            _dotenv_literal(value, "persistent studio key")
            result[name] = value
            preserved.append(name)
        else:
            result[name] = secrets.token_hex(32)
            generated.append(name)
    seed = options.get("admin")
    if seed is None:
        email = prior.get("GAMEFORGE_SEED_ADMIN_EMAIL", "")
        password = prior.get("GAMEFORGE_SEED_ADMIN_PASSWORD", "")
        if not email and not password:
            email = os.environ.get("GAMEFORGE_SEED_ADMIN_EMAIL", "")
            password = os.environ.get("GAMEFORGE_SEED_ADMIN_PASSWORD", "")
        if email or password:
            try:
                seed = _operator_admin_values(email, password)
            except (ValueError, UnicodeError) as exc:
                raise ConfigurationError("existing admin bootstrap values require a separate intentional repair") from exc
    if seed is not None:
        for name, value in zip(("GAMEFORGE_SEED_ADMIN_EMAIL", "GAMEFORGE_SEED_ADMIN_PASSWORD"), seed):
            inherited = os.environ.get(name)
            if inherited is not None and inherited != value:
                raise ConfigurationError("exported admin bootstrap values conflict with the selected operator account")
            _dotenv_literal(value, "admin bootstrap")
            result[name] = value
    options["admin_bootstrap_configured"] = seed is not None
    options["engine_credentials_generated"] = "SKL_ENGINE_SERVICE_TOKEN" in generated
    options["persistent_credential_keys_preserved"] = preserved
    options["persistent_credential_keys_generated"] = [*(_MONGO_KEYS if mongo_generated else ()), *generated]
    return result


def _configuration(options: dict) -> tuple[dict[str, str], dict]:
    persistent = _persistent_studio_keys(options)
    values = {
        "ENVIRONMENT": "development",
        "DEBUG": "false",
        "BUILD_TARGET": "development",
        "FRONTEND_BUILD_TARGET": "development",
        "NODE_ENV": "development",
        "BACKEND_PORT": str(options["backend_port"]),
        "SKELETON_PORT": str(options["skeleton_port"]),
        "FRONTEND_PORT": str(options["frontend_port"]),
        "FRONTEND_CONTAINER_PORT": "3000",
        "MONGO_PORT": str(options["mongo_port"]),
        "GAMEFORGE_AUTH_ENFORCE": "1",
        "SKELETON_INTERNAL_URL": "http://skeleton:8001",
        "SKL_ENGINE_SERVICE_PRINCIPAL": "codedock-backend",
        "SKL_ENGINE_ALLOWED_TENANTS_CSV": ",".join(options["tenants"]),
        "SKL_ENGINE_ALLOWED_CAPABILITIES_CSV": "assistant.chat,assistant.compat,assistant.runtime.control",
        "SKL_JEEVES_CANONICAL_CONVERSATIONS": "1",
        "EXPO_PUBLIC_BACKEND_URL": f"http://{options['host']}:{options['backend_port']}",
        "EXPO_PUBLIC_SKELETON_URL": f"http://{options['host']}:{options['skeleton_port']}",
        "AI_PROVIDER": options["provider"],
        "AI_MODEL": options["model"],
        "OPENAI_API_KEY": options["key"],
        "AI_LOCAL_MODEL_PATH": "/app/data/local-model.json" if options["artifact"] else "",
        "AI_LOCAL_DEPLOYMENT_PATH": options.get("local_container_path", "") if options["deployment"] is not None else "",
        "AI_LOCAL_MODEL_CATALOG_PATH": options.get("local_container_path", "") if options["catalog"] is not None else "",
        "AI_LOCAL_MODEL_CACHE_SIZE": "128",
        "AI_LOCAL_MODEL_SEED": "0",
        "AI_SECONDARY_API_KEY": "",
        "AI_SECONDARY_BASE_URL": "",
        "AI_SECONDARY_MODEL": "",
        "AI_VERIFICATION_MODEL": "",
        "EMERGENT_LLM_KEY": "",
        **persistent,
    }
    override = {
        "services": {
            "backend": {
                "environment": {
                    "GAMEFORGE_AUTH_ENFORCE": "1",
                    "GAMEFORGE_JWT_SECRET": "${GAMEFORGE_JWT_SECRET:?private chat signing secret is required}",
                    "DB_NAME": values["MONGO_INITDB_DATABASE"].replace("$", "$$"),
                }
            }
        }
    }
    # Pin the explicit non-secret model choice in the override so unrelated
    # exported model variables cannot silently select another provider/model.
    engine_environment = {key: value.replace("$", "$$") for key, value in values.items() if key in {
        "AI_PROVIDER", "AI_MODEL", "AI_LOCAL_MODEL_PATH", "AI_LOCAL_DEPLOYMENT_PATH",
        "AI_LOCAL_MODEL_CATALOG_PATH", "AI_SECONDARY_API_KEY", "AI_SECONDARY_BASE_URL",
        "AI_SECONDARY_MODEL", "AI_VERIFICATION_MODEL", "EMERGENT_LLM_KEY",
    }}
    if options["provider"] == "local":
        engine_environment["OPENAI_API_KEY"] = ""
    override["services"]["skeleton"] = {"environment": engine_environment}
    if options["artifact"] is not None:
        override["services"]["skeleton"]["volumes"] = [
            _local_binding(options["artifact"], "/app/data/local-model.json")
        ]
    elif options["local_bindings"]:
        override["services"]["skeleton"]["volumes"] = options["local_bindings"]
    if options["local_platform"] is not None:
        override["services"]["skeleton"]["platform"] = options["local_platform"]
    return values, override


def _startup_instructions(options: dict) -> str:
    compose = (
        "docker compose --project-directory "
        + shlex.quote(str(ROOT))
        + " --env-file "
        + shlex.quote(str(options["env_file"]))
        + " -f "
        + shlex.quote(str(ROOT / "docker-compose.yml"))
        + " -f "
        + shlex.quote(str(options["override"]))
    )
    frontend = f"http://{options['host']}:{options['frontend_port']}"
    backend = f"http://{options['host']}:{options['backend_port']}"
    credential_note = (
        "A hosted key was supplied. Presence is recorded; its validity has not been checked."
        if options["key"]
        else (
            "Hosted credentials are absent. Put a real key in the selected environment variable and intentionally regenerate the configuration before expecting hosted chat."
            if options["provider"] == "openai"
            else (
                "The supplied deployment/catalog was prepared for the engine container with exact source file bindings. Model and executable pins are preserved; the engine performs activation admission during startup. No provider credentials are required."
                if options["deployment"] is not None or options["catalog"] is not None
                else "The existing artifact is mounted read-only. The engine will validate its format and identity during startup; no provider credentials are required."
            )
        )
    )
    artifact_access = ""
    reader_paths = set(options["local_reader_paths"])
    if options["artifact"] is not None:
        reader_paths.add(options["artifact"])
    if reader_paths:
        executable_paths = set(options["local_executable_paths"])
        grants = "\n".join(
            "setfacl -m u:10001:" + ("rx" if path in executable_paths else "r") + " -- " + shlex.quote(str(path))
            for path in sorted(reader_paths)
        )
        artifact_access = (
            "\nThe engine image runs as UID 10001. On Linux, source files need an existing read grant for that user, and runtime executables also need execute access. "
            "The generator preserves operator file permissions. If access has not already been granted, apply these targeted grants before startup:\n\n```sh\n"
            + grants
            + "\n```\n\nUse the platform's equivalent runtime read/execute grants if POSIX ACLs are unavailable. Generated non-secret portable manifests are mode 0644; private credentials and the Compose override remain 0600.\n"
        )
    platform_note = ""
    if options["local_platform"] is not None:
        platform_note = (
            "\nThe engine container platform is explicitly set to `" + options["local_platform"]
            + "` to match the supplied Linux runtime. Docker must support this platform; cross-architecture emulation can be slower.\n"
        )
    admin_note = (
        "An explicit administrator account is configured through the existing seed owner. Sign in with that account to change runtime policies or restore learning checkpoints."
        if options.get("admin_bootstrap_configured")
        else "Registration creates a viewer account. Administrator-only runtime controls require an explicit operator account. Regenerate with paired `--admin-email operator@example.com --admin-password-file /private/admin-password.txt` options and `--force` to retain existing store and signing credentials. The password file must be private and contain 16 or more characters within 72 UTF-8 bytes. Existing account changes remain governed by the administrator seed owner. No first registrant receives administrator privileges."
    )
    return f"""# Start the configured local chat stack

These files were generated for a local Docker Compose setup on the Docker host.
The environment file contains private credentials; keep its mode 0600 and do not commit it or paste its contents.
{credential_note}
{artifact_access}
{platform_note}
{admin_note}

Start only when you are ready:

```sh
{compose} up -d --build mongo skeleton backend frontend
```

Open {frontend}, create an account or sign in, then open the AI chat workspace.
The generated override enforces authentication and uses a persistent signing secret.
The default allowed tenant is `default`; explicit configured tenant IDs are {', '.join(options['tenants'])}.
The authenticated model catalog is `{backend}/api/ai/models`; it reports real engine readiness after startup.
For a phone or another computer, regenerate using `--public-host` set to a host reachable by that device.

Inspect service startup when needed:

```sh
{compose} logs --tail=100 skeleton backend
```

Log output may contain operational details; inspect it locally before sharing.
No network request, provider call, build, service launch or test was performed by the configuration command.
A local reference/neural artifact is a development baseline; activation does not establish general chat quality or production promotion.

`--force` replaces the selected model configuration and generated files while preserving valid existing MongoDB credentials and URLs, session signing secrets, engine service token, master, seal and studio keyholder material.
A valid existing explicit administrator seed is preserved unless paired replacement administrator options are supplied. An existing hosted key is preserved when no replacement key source is supplied.
Incomplete, malformed or conflicting existing credentials stop configuration generation; they require an explicit repair. Fresh configurations generate new credentials only for identities not already supplied.
The command does not rotate database users, signing identities or service credentials, and does not delete persistent data.
Keep a private copy of the old environment before replacing a configuration already used by a persistent stack.
Perform any intentional credential rotation separately through the owning service.
"""


def _summary(options: dict, *, written: bool) -> dict:
    return {
        "provider": options["provider"],
        "files_written": written,
        "environment_file": str(options["env_file"]),
        "compose_override": str(options["override"]),
        "startup_instructions": str(options["instructions"]),
        "private_file_mode": "0600",
        "hosted_credentials_present": bool(options["key"]),
        "admin_bootstrap_configured": options.get("admin_bootstrap_configured"),
        "admin_bootstrap_requested": options.get("admin") is not None,
        "local_artifact_present": options["artifact"] is not None,
        "local_deployment_present": options["deployment"] is not None,
        "local_catalog_present": options["catalog"] is not None,
        "portable_manifests": [str(path) for path, _raw in options["local_manifests"]],
        "local_container_platform": options["local_platform"],
        "local_artifact_access_verified": False,
        "local_artifact_reader_uid": 10001 if options["artifact"] is not None or options["local_reader_paths"] else None,
        "local_artifact_format_verified": False,
        "provider_access_verified": False,
        "service_readiness_verified": False,
        "engine_credentials_generated": bool(written and options.get("engine_credentials_generated")),
        "database_credentials_generated": bool(written and options.get("database_credentials_generated")),
        "persistent_credential_keys_preserved": options.get("persistent_credential_keys_preserved", []),
        "persistent_credential_keys_generated": options.get("persistent_credential_keys_generated", []) if written else [],
        "public_backend_url": f"http://{options['host']}:{options['backend_port']}",
        "public_frontend_url": f"http://{options['host']}:{options['frontend_port']}",
        "next_step": "Read the private startup instructions; the operator controls service launch.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, help="explicit new private environment file")
    parser.add_argument("--provider", required=True, choices=("openai", "local"))
    parser.add_argument(
        "--openai-key-env", help="name of an existing environment variable containing a real hosted key"
    )
    parser.add_argument(
        "--model", help="optional hosted model identity; omitted uses the canonical engine default"
    )
    local_sources = parser.add_mutually_exclusive_group()
    local_sources.add_argument("--local-artifact", help="existing governed local JSON artifact on the Docker host")
    local_sources.add_argument("--local-deployment", help="existing digest-pinned Linux llama.cpp deployment manifest")
    local_sources.add_argument("--local-catalog", help="existing catalog of 1–8 named, digest-pinned local sources")
    parser.add_argument("--public-host", default="localhost", help="browser/device-reachable hostname or IP")
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--skeleton-port", type=int, default=8010)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--mongo-port", type=int, default=27017)
    parser.add_argument("--tenant", action="append", help="explicit allowed tenant; default is default")
    parser.add_argument("--admin-email", help="explicit operator administrator email; paired with --admin-password-file")
    parser.add_argument("--admin-password-file", help="private UTF-8 password file for the existing administrator seed owner")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace model configuration and outputs while preserving existing persistent credentials",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="configuration-only summary; validate supplied pins, without writes or network"
    )
    args = parser.parse_args(argv)
    try:
        options = _options(args)
        if args.dry_run:
            print(json.dumps(_summary(options, written=False), indent=2))
            return 0
        values, override = _configuration(options)
        # Reuse the canonical setup owner so the default read-only model bind
        # never becomes an unexpected root-owned directory created by Docker.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from skeleton.app.setup_runtime import _prepare_model_directory

        try:
            _prepare_model_directory(ROOT, values)
        except ValueError as exc:
            raise ConfigurationError("the existing local model bind directory could not be prepared safely") from exc
        dotenv = (
            "# Private local chat configuration. Never commit or share this file.\n"
            + "\n".join(key + "=" + _dotenv_literal(value, key) for key, value in values.items())
            + "\n"
        )
        outputs = [
            *((path, raw, 0o644) for path, raw in options["local_manifests"]),
            (options["override"], (json.dumps(override, indent=2) + "\n").encode(), 0o600),
            (options["instructions"], _startup_instructions(options).encode(), 0o600),
            (options["env_file"], dotenv.encode(), 0o600),
        ]
        created = []
        try:
            for path, content, mode in outputs:
                existed = path.exists()
                _private_write(path, content, force=args.force, mode=mode)
                if not existed:
                    created.append(path)
        except Exception:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            raise
        print(json.dumps(_summary(options, written=True), indent=2))
        return 0
    except ConfigurationError as exc:
        # This owner constructs every message from fixed field names; values,
        # exception chains and environment contents are never interpolated.
        print("Chat configuration: " + str(exc), file=sys.stderr)
        return 2
    except OSError:
        print(
            "Chat configuration was not written safely. Check the selected file paths, permissions, provider inputs and overwrite choice.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
