"""Fail-closed CLI diagnostics distinguish input and canonical custody failures."""
from __future__ import annotations

import errno
import json

import pytest

from skeleton.jeeves.worlds import laptop_cli


@pytest.mark.parametrize(("number", "code", "action"), [
    (errno.EACCES, "custody_permission_denied",
     "inspect_canonical_store_permissions_without_removing_locks"),
    (errno.ENOSPC, "custody_storage_exhausted",
     "free_authorized_storage_and_retry_without_discarding_saves"),
    (errno.EROFS, "custody_read_only",
     "use_an_authorized_writable_canonical_store"),
    (errno.EIO, "custody_io_unavailable",
     "inspect_canonical_store_health_and_preserve_existing_saves"),
])
def test_store_errors_are_not_misreported_as_bad_brief(
    monkeypatch, tmp_path, capsys, number, code, action
):
    monkeypatch.setattr(laptop_cli, "_file", lambda _: {"id": "lighthouse"})

    def denied(_root):
        raise OSError(number, "canonical store unavailable")

    monkeypatch.setattr(laptop_cli, "LaptopFlow", denied)
    assert laptop_cli.run([
        "--store", str(tmp_path), "propose", "--brief-file", "brief.json"
    ]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "ok": False, "error": code, "phase": "propose", "next_action": action
    }
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(("number", "code"), [
    (errno.ELOOP, "input_symlink_disallowed"),
    (errno.ENOENT, "input_missing"),
    (errno.EACCES, "input_permission_denied"),
    (errno.EIO, "input_io_unavailable"),
])
def test_untrusted_input_failure_never_initializes_custody(
    monkeypatch, tmp_path, capsys, number, code
):
    def denied(_path):
        raise OSError(number, "brief unavailable")

    def must_not_construct(_root):
        raise AssertionError("store must not be initialized")

    monkeypatch.setattr(laptop_cli, "_file", denied)
    monkeypatch.setattr(laptop_cli, "LaptopFlow", must_not_construct)
    assert laptop_cli.run([
        "--store", str(tmp_path), "propose", "--brief-file", "brief.json"
    ]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["error"] == code
    assert output["phase"] == "propose"
    assert not list(tmp_path.iterdir())


def test_null_json_is_loaded_before_custody_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(laptop_cli, "_file", lambda _: None)

    def denied(_root):
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr(laptop_cli, "LaptopFlow", denied)
    assert laptop_cli.run([
        "--store", str(tmp_path), "propose", "--brief-file", "null.json"
    ]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "custody_storage_exhausted"
