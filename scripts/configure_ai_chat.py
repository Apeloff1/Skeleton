#!/usr/bin/env python3
"""Write private operator configuration for the existing local Compose stack.

This command never starts a service, probes a provider, loads model weights or
prints a credential. Use an existing environment variable to supply a hosted
key, or bind an existing local artifact through the generated Compose override.
"""

from __future__ import annotations

import argparse
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
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_TENANT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,511}\Z")
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?\Z")
_PLACEHOLDER_KEYS = {"sk-your-key-here", "your-key-here", "your_api_key", "changeme", "change-me"}


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


def _private_write(path: Path, content: bytes, *, force: bool) -> None:
    """Install one complete mode-0600 file without following a leaf symlink."""
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
            os.fchmod(handle.fileno(), 0o600)
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


def _options(args) -> dict:
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
    artifact = None
    if args.provider == "local":
        if args.local_artifact is None or args.model is not None or args.openai_key_env is not None:
            raise ConfigurationError(
                "local mode requires an artifact and does not accept a hosted key or model override"
            )
        artifact = _checked_path(Path(args.local_artifact))
        size = artifact.stat().st_size
        if not 1 <= size <= _MAX_ARTIFACT_BYTES:
            raise ConfigurationError("local artifact violates byte bounds")
    else:
        if args.local_artifact is not None:
            raise ConfigurationError("hosted mode does not accept a local artifact")
        variable = args.openai_key_env or "OPENAI_API_KEY"
        if _VARIABLE.fullmatch(variable) is None:
            raise ConfigurationError("hosted key variable name is invalid")
        key = os.environ.get(variable, "")
        if args.openai_key_env is not None and not key:
            raise ConfigurationError("the selected hosted key environment variable is empty")
        _safe_value(key, "hosted key")
        if key.strip().lower() in _PLACEHOLDER_KEYS:
            raise ConfigurationError("a documented placeholder cannot configure hosted credentials")
    if artifact is not None and any(
        artifact == path or (path.exists() and artifact.samefile(path))
        for path in (env_file, override, instructions)
    ):
        raise ConfigurationError("local artifact and configuration outputs must be distinct")
    return {
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
        "provider": args.provider,
    }


def _configuration(options: dict) -> tuple[dict[str, str], dict]:
    mongo_password = secrets.token_urlsafe(48)
    mongo_user = "chat_admin"
    mongo_auth = quote(mongo_user, safe="") + ":" + quote(mongo_password, safe="") + "@mongo:27017/"
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
        "MONGO_INITDB_ROOT_USERNAME": mongo_user,
        "MONGO_INITDB_ROOT_PASSWORD": mongo_password,
        "MONGO_INITDB_DATABASE": "tutolage",
        "MONGO_URL": "mongodb://" + mongo_auth + "tutolage?authSource=admin",
        "SKL_MONGO_URI": "mongodb://" + mongo_auth + "skeleton?authSource=admin",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "GAMEFORGE_JWT_SECRET": secrets.token_urlsafe(48),
        "GAMEFORGE_AUTH_ENFORCE": "1",
        "SKELETON_INTERNAL_URL": "http://skeleton:8001",
        "SKL_ENGINE_SERVICE_TOKEN": secrets.token_urlsafe(48),
        "SKL_ENGINE_SERVICE_PRINCIPAL": "codedock-backend",
        "SKL_ENGINE_ALLOWED_TENANTS_CSV": ",".join(options["tenants"]),
        "SKL_ENGINE_ALLOWED_CAPABILITIES_CSV": "assistant.chat,assistant.compat",
        "SKL_JEEVES_CANONICAL_CONVERSATIONS": "1",
        "EXPO_PUBLIC_BACKEND_URL": f"http://{options['host']}:{options['backend_port']}",
        "EXPO_PUBLIC_SKELETON_URL": f"http://{options['host']}:{options['skeleton_port']}",
        "AI_PROVIDER": options["provider"],
        "AI_MODEL": options["model"],
        "OPENAI_API_KEY": options["key"],
        "AI_LOCAL_MODEL_PATH": "/app/data/local-model.json" if options["artifact"] else "",
        "AI_LOCAL_DEPLOYMENT_PATH": "",
        "AI_LOCAL_MODEL_CATALOG_PATH": "",
        "AI_LOCAL_MODEL_CACHE_SIZE": "128",
        "AI_LOCAL_MODEL_SEED": "0",
        "AI_SECONDARY_API_KEY": "",
        "AI_SECONDARY_BASE_URL": "",
        "AI_SECONDARY_MODEL": "",
        "AI_VERIFICATION_MODEL": "",
        "EMERGENT_LLM_KEY": "",
    }
    override = {
        "services": {
            "backend": {
                "environment": {
                    "GAMEFORGE_AUTH_ENFORCE": "1",
                    "GAMEFORGE_JWT_SECRET": "${GAMEFORGE_JWT_SECRET:?private chat signing secret is required}",
                    "DB_NAME": "tutolage",
                }
            }
        }
    }
    if options["artifact"] is not None:
        override["services"]["skeleton"] = {
            "volumes": [
                {
                    "type": "bind",
                    "source": str(options["artifact"]),
                    "target": "/app/data/local-model.json",
                    "read_only": True,
                    "bind": {"create_host_path": False},
                }
            ]
        }
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
            else "The existing artifact is mounted read-only. The engine will validate its format and identity during startup; no provider credentials are required."
        )
    )
    artifact_access = ""
    if options["artifact"] is not None:
        artifact_access = (
            "\nThe engine image runs as UID 10001. On Linux, a private artifact exported as mode 0600 needs read access for that UID. "
            "Grant access only to that runtime user before startup; the generator does not change artifact permissions:\n\n```sh\n"
            + "setfacl -m u:10001:r -- "
            + shlex.quote(str(options["artifact"]))
            + "\n```\n\nUse your platform's equivalent private read grant if POSIX ACLs are unavailable.\n"
        )
    return f"""# Start the configured local chat stack

These files were generated for a local Docker Compose setup on the Docker host.
The environment file contains private credentials; keep its mode 0600 and do not commit it or paste its contents.
{credential_note}
{artifact_access}

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

`--force` replaces files and generates new signing, engine and MongoDB secrets.
It does not rotate users in existing MongoDB volumes or delete persistent data.
Keep a private copy of the old environment before replacing a configuration already used by a persistent stack.
Use a fresh local stack for new bootstrap credentials, or perform an explicit database credential rotation separately.
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
        "local_artifact_present": options["artifact"] is not None,
        "local_artifact_access_verified": False,
        "local_artifact_reader_uid": 10001 if options["artifact"] is not None else None,
        "local_artifact_format_verified": False,
        "provider_access_verified": False,
        "service_readiness_verified": False,
        "engine_credentials_generated": written,
        "database_credentials_generated": written,
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
    parser.add_argument("--local-artifact", help="existing governed local artifact on the Docker host")
    parser.add_argument("--public-host", default="localhost", help="browser/device-reachable hostname or IP")
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--skeleton-port", type=int, default=8010)
    parser.add_argument("--frontend-port", type=int, default=3000)
    parser.add_argument("--mongo-port", type=int, default=27017)
    parser.add_argument("--tenant", action="append", help="explicit allowed tenant; default is default")
    parser.add_argument(
        "--force",
        action="store_true",
        help="intentionally replace outputs; does not rotate existing database users",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="presence-only summary, no file writes or network"
    )
    args = parser.parse_args(argv)
    try:
        options = _options(args)
        if args.dry_run:
            print(json.dumps(_summary(options, written=False), indent=2))
            return 0
        values, override = _configuration(options)
        dotenv = (
            "# Private local chat configuration. Never commit or share this file.\n"
            + "\n".join(key + "='" + _safe_value(value, key) + "'" for key, value in values.items())
            + "\n"
        )
        outputs = [
            (options["override"], (json.dumps(override, indent=2) + "\n").encode()),
            (options["instructions"], _startup_instructions(options).encode()),
            (options["env_file"], dotenv.encode()),
        ]
        created = []
        try:
            for path, content in outputs:
                existed = path.exists()
                _private_write(path, content, force=args.force)
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
