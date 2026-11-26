"""``<NAME>_FILE`` secret mounts for the GameForge auth configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.auth_security import (
    AuthConfigurationError,
    read_secret,
    resolve_jwt_secret,
    resolve_seed_admin,
    security_summary,
)

STRONG_SECRET = "f" * 48
PASSWORD = "Correct-Horse-Battery-Staple-2026"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_env_value_is_used_when_no_file_is_configured():
    assert read_secret("GAMEFORGE_JWT_SECRET", {"GAMEFORGE_JWT_SECRET": "abc"}) == "abc"
    assert read_secret("GAMEFORGE_JWT_SECRET", {}) == ""


def test_file_mount_supplies_jwt_secret_in_production(tmp_path: Path):
    secret_file = _write(tmp_path / "jwt", STRONG_SECRET + "\n")
    environ = {"APP_ENV": "production", "GAMEFORGE_JWT_SECRET_FILE": str(secret_file)}
    assert resolve_jwt_secret(environ) == STRONG_SECRET
    assert security_summary(environ)["jwt_secret_configured"] is True
    assert STRONG_SECRET not in repr(security_summary(environ))


def test_only_one_trailing_newline_is_stripped(tmp_path: Path):
    assert read_secret("X", {"X_FILE": str(_write(tmp_path / "a", "v\r\n"))}) == "v"
    assert read_secret("X", {"X_FILE": str(_write(tmp_path / "b", "v\n\n"))}) == "v\n"
    assert read_secret("X", {"X_FILE": str(_write(tmp_path / "c", "v"))}) == "v"


def test_kubernetes_style_symlinked_mount_is_followed(tmp_path: Path):
    data = tmp_path / "..2026_11_22" / "jwt"
    data.parent.mkdir()
    _write(data, STRONG_SECRET)
    (tmp_path / "..data").symlink_to(data.parent.name)
    (tmp_path / "jwt").symlink_to(Path("..data") / "jwt")
    assert (
        resolve_jwt_secret({"APP_ENV": "production", "GAMEFORGE_JWT_SECRET_FILE": str(tmp_path / "jwt")})
        == STRONG_SECRET
    )


def test_weak_file_secret_is_still_rejected(tmp_path: Path):
    environ = {"APP_ENV": "production", "GAMEFORGE_JWT_SECRET_FILE": str(_write(tmp_path / "jwt", "short\n"))}
    with pytest.raises(AuthConfigurationError, match="at least"):
        resolve_jwt_secret(environ)


def test_seed_admin_password_from_file(tmp_path: Path):
    environ = {
        "GAMEFORGE_SEED_ADMIN_EMAIL": "admin@example.com",
        "GAMEFORGE_SEED_ADMIN_PASSWORD_FILE": str(_write(tmp_path / "pw", PASSWORD + "\n")),
    }
    seed = resolve_seed_admin(environ)
    assert seed is not None and seed.password == PASSWORD
    assert PASSWORD not in repr(seed)


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("both", "only one of"),
        ("relative", "absolute path"),
        ("missing", "not readable"),
        ("directory", "regular file"),
        ("oversized", "larger than"),
        ("binary", "UTF-8"),
    ],
)
def test_misconfigured_mounts_fail_closed_without_leaking(tmp_path: Path, setup: str, message: str):
    target = tmp_path / "secret"
    environ: dict[str, str] = {"APP_ENV": "production"}
    if setup == "both":
        _write(target, STRONG_SECRET)
        environ.update(GAMEFORGE_JWT_SECRET=STRONG_SECRET, GAMEFORGE_JWT_SECRET_FILE=str(target))
    elif setup == "relative":
        environ["GAMEFORGE_JWT_SECRET_FILE"] = "secrets/jwt"
    elif setup == "missing":
        environ["GAMEFORGE_JWT_SECRET_FILE"] = str(tmp_path / "absent")
    elif setup == "directory":
        environ["GAMEFORGE_JWT_SECRET_FILE"] = str(tmp_path)
    elif setup == "oversized":
        target.write_bytes(b"x" * (64 * 1024 + 1))
        environ["GAMEFORGE_JWT_SECRET_FILE"] = str(target)
    else:
        target.write_bytes(b"\xff\xfe" + b"s" * 40)
        environ["GAMEFORGE_JWT_SECRET_FILE"] = str(target)
    with pytest.raises(AuthConfigurationError, match=message) as caught:
        resolve_jwt_secret(environ)
    assert STRONG_SECRET not in str(caught.value)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_unreadable_file_is_reported_as_configuration_error(tmp_path: Path):
    target = _write(tmp_path / "jwt", STRONG_SECRET)
    target.chmod(0)
    try:
        with pytest.raises(AuthConfigurationError, match="not readable"):
            read_secret("GAMEFORGE_JWT_SECRET", {"GAMEFORGE_JWT_SECRET_FILE": str(target)})
    finally:
        target.chmod(0o600)
