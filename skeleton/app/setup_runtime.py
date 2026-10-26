"""Configuration bootstrap for the unified Skeleton application.

This layer owns local setup state and secret generation.  It is intentionally
idempotent and never returns secret values in receipts or logs.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote, urlsplit

from skeleton.app.assembly import _dotenv_value, find_repo_root


@dataclass(frozen=True)
class SetupResult:
    env_path: Path
    created: bool
    changed: bool
    configured_keys: tuple[str, ...]
    preserved_keys: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "env_path": str(self.env_path),
            "created": self.created,
            "changed": self.changed,
            "configured_keys": list(self.configured_keys),
            "preserved_keys": list(self.preserved_keys),
            "warnings": list(self.warnings),
        }


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _dotenv_value(value)
    return values


def _is_placeholder(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    # Do not treat the word "example" inside a real Mongo hostname or
    # operator-provided secret as a placeholder (e.g. db.example.net).
    return any(
        token in lowered
        for token in (
            "change-me",
            "changeme",
            "your-key-here",
            "your-secret",
            "replace-me",
        )
    ) or lowered in {"example", "example-value", "example-secret"}


def _bundled_mongo_endpoint(value: str) -> bool:
    """Recognize only the bundled Mongo host, including legacy no-auth URIs.

    Remote database URLs must never be rewritten during setup. URL parsing
    prevents substring matches in external hostnames or credential text.
    """
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "mongodb"
            and parsed.hostname == "mongo"
            and parsed.port in {None, 27017}
        )
    except ValueError:
        return False


def _replace_env_value(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    replacement = f"{key}={value}"
    found = False
    for index, line in enumerate(lines):
        if line.strip().startswith("#") or "=" not in line:
            continue
        existing_key, _ = line.split("=", 1)
        if existing_key.strip() == key:
            lines[index] = replacement
            found = True
    # Compose uses the last assignment. Repair every occurrence so an older
    # duplicate cannot override a generated credential on the next startup.
    if found:
        return "\n".join(lines) + "\n"
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(replacement)
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        # Include temp-file creation, write, flush and fsync in the cleanup
        # boundary. The previous implementation entered try only *after*
        # successful fsync, leaving secret-bearing .env.*.tmp files behind
        # when disks filled or storage synchronization failed.
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _operator_admin_values(email: str, password: str) -> tuple[str, str]:
    """Validate existing explicit seed values without changing their authority."""

    email = email.strip().lower()
    if (
        len(email) > 254
        or email.count("@") != 1
        or any(char.isspace() or ord(char) < 32 for char in email)
        or not all(email.split("@"))
    ):
        raise ValueError("operator admin email must be a valid non-empty email address")
    if (
        len(password) < 16
        or len(password.encode("utf-8")) > 72
        or any(ord(char) < 32 or ord(char) == 127 for char in password)
    ):
        raise ValueError(
            "admin password must contain at least 16 characters, at most 72 UTF-8 bytes and no control characters"
        )
    return email, password


def _operator_admin(email: str | None, password_file: Path | None) -> tuple[str, str] | None:
    """Admit an explicit operator account without exposing a password in argv."""

    if email is None and password_file is None:
        return None
    if email is None or password_file is None:
        raise ValueError("--admin-email and --admin-password-file must be supplied together")
    email = email.strip().lower()
    if (
        len(email) > 254
        or email.count("@") != 1
        or any(char.isspace() or ord(char) < 32 for char in email)
        or not all(email.split("@"))
    ):
        raise ValueError("operator admin email must be a valid non-empty email address")
    descriptor = os.open(Path(password_file).expanduser(), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
            raise ValueError("admin password input must be a regular file of at most 4096 bytes")
        if os.name != "nt" and info.st_mode & 0o077:
            raise ValueError("admin password file must be private; run chmod 600 on that file")
        raw = handle.read(4097)
    if len(raw) > 4096:
        raise ValueError("admin password file exceeds 4096 bytes")
    try:
        password = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("admin password file must contain UTF-8 text") from None
    if password.endswith("\r\n"):
        password = password[:-2]
    elif password.endswith("\n"):
        password = password[:-1]
    return _operator_admin_values(email, password)


def _prepare_model_directory(root: Path, values: dict[str, str]) -> bool:
    """Prepare the operator's bind root before Docker can create it as root."""

    raw = os.environ.get("SKELETON_LOCAL_MODEL_DIR", values.get("SKELETON_LOCAL_MODEL_DIR", ""))
    raw = raw.strip() or "./data/local-ai"
    if "\x00" in raw or len(raw) > 4096:
        raise ValueError("SKELETON_LOCAL_MODEL_DIR must be a valid local directory path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    if path.is_symlink():
        raise ValueError("SKELETON_LOCAL_MODEL_DIR must name a real directory, not a symbolic link")
    created = False
    try:
        path.mkdir(parents=True, mode=0o755)
        path.chmod(0o755)
        created = True
    except FileExistsError:
        if not path.is_dir():
            raise ValueError("SKELETON_LOCAL_MODEL_DIR exists but is not a directory") from None
    except OSError:
        raise ValueError(
            "Cannot prepare SKELETON_LOCAL_MODEL_DIR; choose an operator-owned directory and check parent permissions"
        ) from None
    try:
        empty = next(path.iterdir(), None) is None
    except OSError:
        raise ValueError("SKELETON_LOCAL_MODEL_DIR must be readable by the operator") from None
    if empty and not os.access(path, os.W_OK | os.X_OK):
        raise ValueError(
            "Empty SKELETON_LOCAL_MODEL_DIR is not writable; select an operator-owned directory or repair its ownership before provisioning"
        )
    return created


def ensure_runtime_environment(
    root: Path | None = None,
    *,
    rotate_secrets: bool = False,
    admin_email: str | None = None,
    admin_password_file: Path | None = None,
) -> SetupResult:
    """Create or repair .env without overwriting valid existing values."""

    root = (root or find_repo_root()).resolve()
    operator_admin = _operator_admin(admin_email, admin_password_file)
    env_path = root / ".env"
    example_path = root / ".env.example"
    created = not env_path.exists()
    warnings: list[str] = []

    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
    elif example_path.is_file():
        text = example_path.read_text(encoding="utf-8")
    else:
        text = (
            "# Generated by Skeleton application setup\n"
            "MONGO_INITDB_ROOT_USERNAME=admin\n"
            "MONGO_INITDB_ROOT_PASSWORD=\n"
            "MONGO_URL=\n"
            "SKL_MONGO_URI=\n"
            "JWT_SECRET=\n"
        )
        warnings.append(".env.example was missing; generated a minimal runtime template")

    values = _parse_env(text)
    configured: list[str] = []
    preserved: list[str] = []
    if operator_admin is not None:
        email, password = operator_admin
        for key, value in (
            ("GAMEFORGE_SEED_ADMIN_EMAIL", email),
            ("GAMEFORGE_SEED_ADMIN_PASSWORD", password),
        ):
            if values.get(key) == value:
                preserved.append(key)
            else:
                # Compose interpolates unquoted/double-quoted dollar values.
                # JSON quoting plus escaped dollar pairs preserves exact bytes.
                literal = json.dumps(value, ensure_ascii=False).replace("$", "$$")
                text = _replace_env_value(text, key, literal)
                values[key] = value
                configured.append(key)

    username = values.get("MONGO_INITDB_ROOT_USERNAME", "admin").strip() or "admin"
    if not values.get("MONGO_INITDB_ROOT_USERNAME", "").strip():
        text = _replace_env_value(text, "MONGO_INITDB_ROOT_USERNAME", username)
        values["MONGO_INITDB_ROOT_USERNAME"] = username
        configured.append("MONGO_INITDB_ROOT_USERNAME")

    password = values.get("MONGO_INITDB_ROOT_PASSWORD", "")
    # MongoDB's root user is initialized only when its persistent data volume
    # is empty. Changing .env alone does NOT rotate the database user password.
    # Generic --rotate-secrets must preserve existing credentials; database
    # password rotation needs a separate authenticated DB operation.
    if _is_placeholder(password):
        password = secrets.token_urlsafe(24)
        text = _replace_env_value(text, "MONGO_INITDB_ROOT_PASSWORD", password)
        values["MONGO_INITDB_ROOT_PASSWORD"] = password
        configured.append("MONGO_INITDB_ROOT_PASSWORD")
    else:
        preserved.append("MONGO_INITDB_ROOT_PASSWORD")

    jwt_secret = values.get("JWT_SECRET", "")
    if rotate_secrets or _is_placeholder(jwt_secret) or not 32 <= len(jwt_secret) <= 4096:
        jwt_secret = secrets.token_hex(32)
        text = _replace_env_value(text, "JWT_SECRET", jwt_secret)
        values["JWT_SECRET"] = jwt_secret
        configured.append("JWT_SECRET")
    else:
        preserved.append("JWT_SECRET")

    # The backend and engine must share this value before Compose can start.
    # Upgrade existing .env files as well as templates predating Stage-5.
    service_token = values.get("SKL_ENGINE_SERVICE_TOKEN", "")
    if (
        rotate_secrets
        or _is_placeholder(service_token)
        or not 32 <= len(service_token) <= 4096
        or service_token != service_token.strip()
    ):
        service_token = secrets.token_hex(32)
        text = _replace_env_value(text, "SKL_ENGINE_SERVICE_TOKEN", service_token)
        values["SKL_ENGINE_SERVICE_TOKEN"] = service_token
        configured.append("SKL_ENGINE_SERVICE_TOKEN")
    else:
        preserved.append("SKL_ENGINE_SERVICE_TOKEN")

    # The installed game-production stack needs stable secret protection,
    # Forge HMAC identity and process signing across restarts. An empty seed
    # makes the signing identity ephemeral and can invalidate earlier evidence.
    # These are generated once; ordinary secret rotation must NEVER replace
    # keys protecting stored ciphertext or signed historical artifacts.
    for key in (
        "SKELETON_MASTER_SECRET",
        "GF_SEAL_SECRET",
        "GF_KEYHOLDER_SEED",
        "GAMEFORGE_JWT_SECRET",
    ):
        current = values.get(key, "")
        if _is_placeholder(current):
            generated = secrets.token_hex(32)
            text = _replace_env_value(text, key, generated)
            values[key] = generated
            configured.append(key)
        else:
            preserved.append(key)

    signing_seed = values["GF_KEYHOLDER_SEED"]
    if len(signing_seed) != 64 or any(c not in "0123456789abcdefABCDEF" for c in signing_seed):
        warnings.append("GF_KEYHOLDER_SEED must be exactly 32 bytes of hexadecimal data")
    # Existing operator signing identities must never be silently replaced.
    # Invalid non-placeholder keys are retained and reported for preflight.
    gameforge_secret = values["GAMEFORGE_JWT_SECRET"]
    if not 32 <= len(gameforge_secret) <= 4096:
        warnings.append("GAMEFORGE_JWT_SECRET must contain 32 to 4096 characters")

    user_uri = quote(username, safe="")
    password_uri = quote(password, safe="")

    mongo_authority = "mongodb://" + user_uri + ":" + password_uri + "@mongo:27017/"
    generated_uris = {
        "MONGO_URL": mongo_authority + "tutolage?authSource=admin",
        "SKL_MONGO_URI": mongo_authority + "skeleton?authSource=admin",
    }
    for key, generated in generated_uris.items():
        current = values.get(key, "")
        local_generated_uri = _bundled_mongo_endpoint(current)
        # A remote URI may legitimately contain "change-me" in its hostname
        # or credential. Never redirect any operator-supplied remote Mongo
        # endpoint to the bundled database, even if a placeholder token
        # appears within that URI. Malformed/weak remote config fails the
        # separate runtime preflight rather than silently changing ownership.
        current_is_mongo_uri = current.lower().startswith(
            ("mongodb://", "mongodb+srv://")
        )
        if (
            (not current_is_mongo_uri and _is_placeholder(current))
            or (local_generated_uri and current != generated)
        ):
            text = _replace_env_value(text, key, generated)
            values[key] = generated
            configured.append(key)
        else:
            preserved.append(key)

    for key in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY", "STRIPE_API_KEY"):
        current = values.get(key, "")
        if current and _is_placeholder(current):
            text = _replace_env_value(text, key, "")
            values[key] = ""
            configured.append(key)
        if not values.get(key, ""):
            warnings.append(f"{key} remains optional and unconfigured")

    if not values.get("AI_PROVIDER", "").strip():
        # Preserve existing genuine hosted configuration on upgrades. Clean
        # installations need neither a provider credential nor invented weights.
        provider = (
            "openai" if any(values.get(key) for key in ("OPENAI_API_KEY", "EMERGENT_LLM_KEY")) else "local"
        )
        text = _replace_env_value(text, "AI_PROVIDER", provider)
        values["AI_PROVIDER"] = provider
        configured.append("AI_PROVIDER")
    if values["AI_PROVIDER"].strip().lower() == "local":
        local_configurations = sum(bool(values.get(key, "").strip()) for key in (
            "AI_LOCAL_MODEL_PATH", "AI_LOCAL_DEPLOYMENT_PATH", "AI_LOCAL_MODEL_CATALOG_PATH",
        ))
        if local_configurations == 0:
            warnings.append(
                "AI is unavailable until a local artifact, deployment or model catalog is configured; application services can still start"
            )
        elif local_configurations > 1:
            warnings.append(
                "Local AI configuration conflicts: choose exactly one of AI_LOCAL_MODEL_PATH, AI_LOCAL_DEPLOYMENT_PATH or AI_LOCAL_MODEL_CATALOG_PATH; existing operator values were preserved"
            )

    if _prepare_model_directory(root, values):
        warnings.append("Local AI mount directory prepared; no model files acquired or provider activated")

    changed = created or bool(configured)
    if changed:
        _atomic_write(env_path, text)

    return SetupResult(
        env_path=env_path,
        created=created,
        changed=changed,
        configured_keys=tuple(dict.fromkeys(configured)),
        preserved_keys=tuple(dict.fromkeys(preserved)),
        warnings=tuple(warnings),
    )
