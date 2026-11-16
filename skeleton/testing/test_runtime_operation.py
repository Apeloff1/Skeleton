"""Real OS lifecycle lease regression tests, without Docker or credentials."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys

import pytest
from skeleton.app import runtime_operation as op


@pytest.mark.parametrize("first",sorted(op.OPERATIONS))
@pytest.mark.parametrize("second",sorted(op.OPERATIONS))
def test_every_lifecycle_operation_is_mutually_exclusive(tmp_path,first,second):
    with op.runtime_operation(tmp_path,first,wait_seconds=0) as lease:
        assert lease.current()
        with pytest.raises(op.RuntimeOperationDenied,match="another installation operation"):
            with op.runtime_operation(tmp_path,second,wait_seconds=0):
                pytest.fail("competing operation admitted")
    with op.runtime_operation(tmp_path,second,wait_seconds=0) as lease:
        assert lease.current()
    assert (tmp_path/op.LOCK_NAME).read_bytes()==b"\0"


def test_lock_survives_exception_and_keeps_inode(tmp_path):
    with pytest.raises(RuntimeError,match="fixture"):
        with op.runtime_operation(tmp_path,"install") as lease:
            first=lease.file_identity
            raise RuntimeError("fixture")
    with op.runtime_operation(tmp_path,"stop") as lease:
        assert lease.file_identity==first


def test_cross_process_contention_and_process_exit_release(tmp_path):
    code=("from pathlib import Path; from skeleton.app.runtime_operation import runtime_operation; "
          "import sys; "
          "lease=runtime_operation(Path(sys.argv[1]),'install',wait_seconds=0); "
          "lease.__enter__(); print('held',flush=True); sys.stdin.read(1)")
    repo=Path(__file__).resolve().parents[2]
    child=subprocess.Popen([sys.executable,"-c",code,str(tmp_path)],cwd=repo,
                           stdout=subprocess.PIPE,stdin=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        # Use a bounded subprocess observation instead of waiting indefinitely
        # for a failed import; readiness is communicated by an OS lock attempt.
        import time
        deadline=time.monotonic()+10
        held=False
        while time.monotonic()<deadline and child.poll() is None:
            try:
                with op.runtime_operation(tmp_path,"stop",wait_seconds=0):
                    pass
            except op.RuntimeOperationDenied:
                held=True
                break
            time.sleep(.05)
        assert held
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
    with op.runtime_operation(tmp_path,"start",wait_seconds=0) as lease:
        assert lease.current()


def test_linked_lock_does_not_touch_external_file(tmp_path):
    target=tmp_path/"external"
    target.write_bytes(b"\0")
    path=tmp_path/op.LOCK_NAME
    try:
        path.symlink_to(target)
    except (OSError,NotImplementedError):
        pytest.skip("symlink support unavailable")
    with pytest.raises(op.RuntimeOperationDenied):
        with op.runtime_operation(tmp_path,"setup"):
            pytest.fail("linked operation lock admitted")
    assert target.read_bytes()==b"\0"


@pytest.mark.parametrize("contents",[b"x",b"\0\0",b"private-text"])
def test_invalid_lock_content_is_preserved(tmp_path,contents):
    path=tmp_path/op.LOCK_NAME
    path.write_bytes(contents)
    path.chmod(0o600)
    with pytest.raises(op.RuntimeOperationDenied):
        with op.runtime_operation(tmp_path,"start"):
            pytest.fail("invalid runtime lock admitted")
    assert path.read_bytes()==contents


def test_compose_lifecycle_policy_preserves_project_and_context_but_not_orphan_override():
    source={"COMPOSE_ENV_FILES":"unexpected","COMPOSE_REMOVE_ORPHANS":"1",
            "COMPOSE_PROFILES":"full","COMPOSE_DISABLE_ENV_FILE":"1",
            "COMPOSE_PROJECT_NAME":"existing-project","DOCKER_CONTEXT":"desktop-linux"}
    env=op.compose_operation_environment(source,{"BUILD_TARGET":"production"})
    assert env["COMPOSE_REMOVE_ORPHANS"]=="0"
    assert env["COMPOSE_PROFILES"]==""
    assert env["COMPOSE_DISABLE_ENV_FILE"]=="0"
    assert "COMPOSE_ENV_FILES" not in env
    assert env["COMPOSE_PROJECT_NAME"]=="existing-project"
    assert env["DOCKER_CONTEXT"]=="desktop-linux"
    assert env["BUILD_TARGET"]=="production"
    assert source["COMPOSE_REMOVE_ORPHANS"]=="1"
