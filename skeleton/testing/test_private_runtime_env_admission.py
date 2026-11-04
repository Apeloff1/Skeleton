"""Fail-closed private runtime environment admission for installer URL probes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skeleton.app.assembly import _read_dotenv, load_manifest, public_service_urls


def test_missing_private_env_is_optional(tmp_path: Path) -> None:
    assert _read_dotenv(tmp_path / ".env") == {}
    assert "backend" in public_service_urls(tmp_path, manifest=load_manifest(), environ={})


def test_private_env_regular_file_reads_expected_values(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("# comment\nBACKEND_PORT=8123\n", encoding="utf-8")
    assert _read_dotenv(path)["BACKEND_PORT"] == "8123"
    urls = public_service_urls(tmp_path, manifest=load_manifest(), environ={})
    assert urls["backend"].endswith(":8123")


def test_private_env_rejects_symlink_without_disclosing_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("JWT_SECRET=private-value\n", encoding="utf-8")
    try:
        (tmp_path / ".env").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="regular file"):
        _read_dotenv(tmp_path / ".env")
    assert target.read_text(encoding="utf-8") == "JWT_SECRET=private-value\n"


def test_private_env_rejects_oversize(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_bytes(b"A" * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="256 KiB"):
        _read_dotenv(path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX hardlinks and FIFO")
def test_private_env_rejects_hardlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("BACKEND_PORT=8123\n", encoding="utf-8")
    os.link(target, tmp_path / ".env")
    with pytest.raises(ValueError, match="regular file"):
        _read_dotenv(tmp_path / ".env")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO unavailable")
def test_private_env_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        _read_dotenv(path)


def test_invalid_utf8_private_env_fails_closed(tmp_path: Path) -> None:
    (tmp_path / ".env").write_bytes(b"BACKEND_PORT=\xff")
    with pytest.raises(UnicodeDecodeError):
        _read_dotenv(tmp_path / ".env")


def test_private_env_disappears_after_lstat_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / ".env"
    path.write_text("BACKEND_PORT=8123\n", encoding="utf-8")
    original_open = os.open

    def disappearing_open(candidate: os.PathLike[str] | str, flags: int, *args: object, **kwargs: object) -> int:
        if os.fspath(candidate) == os.fspath(path):
            path.unlink()
            raise FileNotFoundError(os.fspath(path))
        return original_open(candidate, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", disappearing_open)
    with pytest.raises(ValueError, match="changed during admission"):
        _read_dotenv(path)
