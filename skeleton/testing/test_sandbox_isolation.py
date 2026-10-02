"""B082: filesystem jail and process isolation."""
from __future__ import annotations

import os
import sys

import pytest

from skeleton.sandbox.errors import FsPolicyError, PathEscapeError, ProcessPolicyError, QuotaExceededError
from skeleton.sandbox.fs import FsJail, JailPolicy, check_relative
from skeleton.sandbox.process import ProcessLimits, check_argv, run_isolated, scrub_env

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX isolation")


@pytest.fixture()
def jail(tmp_path):
    return FsJail(tmp_path / "root")


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd", "C:\\win", "~/x", "a\x00b", "//host/share", "..", "a/..", "con.txt", "a/b. "])
def test_check_relative_rejects(bad: str) -> None:
    with pytest.raises((PathEscapeError, FsPolicyError)):
        check_relative(bad)


def test_check_relative_accepts_and_normalises() -> None:
    assert str(check_relative("a/./b//c.txt")) == "a/b/c.txt"
    assert str(check_relative("a\\b")) == "a/b"


def test_fullwidth_traversal_is_refused() -> None:
    with pytest.raises(PathEscapeError):
        check_relative("\uff0e\uff0e/etc")


def test_roundtrip_and_listing(jail: FsJail) -> None:
    assert jail.write_text("dir/a.txt", "hello") == 5
    assert jail.read_text("dir/a.txt") == "hello"
    assert jail.listdir() == ["dir"] and jail.listdir("dir") == ["a.txt"]
    assert jail.exists("dir/a.txt") and not jail.exists("../x")
    jail.delete("dir/a.txt")
    assert not jail.exists("dir/a.txt")


def test_hidden_paths_refused_by_default(jail: FsJail) -> None:
    with pytest.raises(FsPolicyError):
        jail.write_text(".env", "x")


@posix_only
def test_symlink_escape_is_refused(jail: FsJail, tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    os.symlink(outside, jail.root / "link")
    with pytest.raises(PathEscapeError):
        jail.read_text("link/secret.txt")
    with pytest.raises(PathEscapeError):
        jail.write_text("link/new.txt", "x")
    assert not (outside / "new.txt").exists()


@posix_only
def test_internal_symlink_allowed_and_leaf_symlink_unlinked_not_followed(jail: FsJail, tmp_path) -> None:
    jail.write_text("real/a.txt", "ok")
    os.symlink(jail.root / "real", jail.root / "alias")
    assert jail.read_text("alias/a.txt") == "ok"
    target = tmp_path / "victim.txt"
    target.write_text("keep")
    os.symlink(target, jail.root / "leaf")
    jail.delete("leaf")
    assert target.read_text() == "keep"


@posix_only
def test_reading_non_regular_files_refused(jail: FsJail) -> None:
    os.mkfifo(jail.root / "pipe")
    with pytest.raises((FsPolicyError, OSError)):
        jail.read_bytes("pipe")


def test_quotas(tmp_path) -> None:
    j = FsJail(tmp_path / "q", JailPolicy(max_bytes=10, max_files=2, max_file_bytes=8))
    j.write_bytes("a", b"12345")
    with pytest.raises(QuotaExceededError):
        j.write_bytes("b", b"123456789")
    with pytest.raises(QuotaExceededError):
        j.write_bytes("b", b"123456")
    j.write_bytes("a", b"1234567")  # overwrite credits the old size
    j.write_bytes("b", b"1")
    with pytest.raises(QuotaExceededError):
        j.write_bytes("c", b"")
    with pytest.raises(QuotaExceededError):
        j.read_bytes("a", limit=2)


def test_read_only_jail(tmp_path) -> None:
    j = FsJail(tmp_path / "ro", JailPolicy(read_only=True))
    with pytest.raises(FsPolicyError):
        j.write_text("a", "x")


def test_scrub_env_drops_secrets() -> None:
    env = scrub_env({"MODE": "test"}, base={"PATH": "/bin", "GITHUB_TOKEN": "x", "AWS_SECRET_ACCESS_KEY": "y", "LANG": "C"})
    assert env["MODE"] == "test" and "GITHUB_TOKEN" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    with pytest.raises(ProcessPolicyError):
        scrub_env({"API_KEY": "nope"})


def test_argv_policy() -> None:
    for bad in ("ls -la", [], ["a\x00"], [1]):
        with pytest.raises(ProcessPolicyError):
            check_argv(bad)


@posix_only
def test_process_runs_in_jail_with_clean_env(jail: FsJail, monkeypatch) -> None:
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak")
    r = run_isolated([sys.executable, "-c", "import os,json;print(json.dumps([os.getcwd(), dict(os.environ)]))"], jail=jail)
    assert r.ok, r.stderr
    import json

    cwd, env = json.loads(r.text())
    assert os.path.realpath(cwd) == str(jail.root)
    assert "SUPER_SECRET_TOKEN" not in env and env["HOME"] == str(jail.root)


@posix_only
def test_process_timeout_kills_group(jail: FsJail) -> None:
    code = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);time.sleep(60)"
    r = run_isolated([sys.executable, "-c", code], jail=jail, limits=ProcessLimits(wall_seconds=1.0))
    assert r.timed_out and not r.ok
    assert r.duration_s < 10


@posix_only
def test_memory_and_file_size_limits(jail: FsJail) -> None:
    r = run_isolated([sys.executable, "-c", "x = bytearray(3 * 1024**3)"], jail=jail, limits=ProcessLimits(memory_bytes=256 * 1024**2))
    assert r.returncode != 0 and b"MemoryError" in r.stderr
    r2 = run_isolated([sys.executable, "-c", "open('big','wb').write(b'x' * (4 * 1024**2))"], jail=jail, limits=ProcessLimits(file_bytes=1024**2))
    assert r2.returncode != 0
    assert os.path.getsize(jail.root / "big") <= 1024**2


@posix_only
def test_output_is_truncated_not_buffered(jail: FsJail) -> None:
    r = run_isolated([sys.executable, "-c", "import sys;sys.stdout.write('x' * 500000)"], jail=jail, limits=ProcessLimits(output_bytes=1000))
    assert r.truncated and len(r.stdout) == 1000


@posix_only
def test_stdin_and_record(jail: FsJail) -> None:
    r = run_isolated([sys.executable, "-c", "import sys;print(sys.stdin.read().upper())"], jail=jail, stdin=b"abc")
    assert r.text().strip() == "ABC"
    rec = r.to_record()
    assert rec["returncode"] == 0 and rec["limits"]["network"] == "inherit"


def test_missing_executable_and_bad_cwd(jail: FsJail) -> None:
    with pytest.raises(ProcessPolicyError):
        run_isolated(["/nonexistent/binary-xyz"], jail=jail)
    with pytest.raises((FsPolicyError, PathEscapeError)):
        run_isolated(["true"], jail=jail, cwd="../")


@posix_only
def test_network_deny_fails_closed_or_isolates(jail: FsJail) -> None:
    from skeleton.sandbox.process import network_isolation_available

    lim = ProcessLimits(network="deny")
    if not network_isolation_available():
        with pytest.raises(ProcessPolicyError):
            run_isolated(["true"], jail=jail, limits=lim)
    else:
        code = "import socket\ntry:\n socket.create_connection(('1.1.1.1', 53), timeout=1); print('net')\nexcept OSError: print('nonet')"
        assert run_isolated([sys.executable, "-c", code], jail=jail, limits=lim).text().strip() == "nonet"
