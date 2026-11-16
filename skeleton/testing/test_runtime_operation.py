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
          "lease=runtime_operation(Path(sys.argv[1]),'install',wait_seconds=5); "
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



@pytest.mark.parametrize("status",[0,1,255])
def test_definite_compose_status_clears_intent(tmp_path,status):
    from types import SimpleNamespace
    from skeleton.app import runtime_mutation as mutation
    with op.runtime_operation(tmp_path,"start") as lease:
        def runner():
            assert mutation.pending(lease)[0]["mutation"]=="compose-start"
            return SimpleNamespace(returncode=status)
        assert mutation.run_mutation(lease,"compose-start",runner).returncode==status
        assert mutation.pending(lease) is None


@pytest.mark.parametrize("status",[None,False,True,"0",-9,256,2**31])
def test_uncertain_compose_status_blocks_later_lifecycle_operations(tmp_path,status):
    from types import SimpleNamespace
    from skeleton.app import runtime_mutation as mutation
    with op.runtime_operation(tmp_path,"start") as lease:
        mutation.run_mutation(lease,"compose-start",lambda:SimpleNamespace(returncode=status))
    record=mutation.recovery_status(tmp_path)
    assert record["pending"] and record["mutation"]=="compose-start"
    assert record["daemon_idle_verified"] is False
    for operation in op.OPERATIONS:
        with pytest.raises(op.RuntimeOperationDenied,match="previous runtime mutation"):
            with op.runtime_operation(tmp_path,operation):
                pytest.fail("uncertain mutation admitted")


def test_timeout_preserves_exact_intent_until_explicit_ack(tmp_path):
    from skeleton.app import runtime_mutation as mutation
    def fail():
        raise subprocess.TimeoutExpired(["docker"],3)
    with pytest.raises(subprocess.TimeoutExpired):
        with op.runtime_operation(tmp_path,"install") as lease:
            mutation.run_mutation(lease,"compose-start",fail)
    before=mutation.recovery_status(tmp_path)
    ident=before["operation_id"]
    for candidate,ack in [(ident,False),("0"*32,True)]:
        with pytest.raises(op.RuntimeOperationDenied):
            mutation.acknowledge(tmp_path,candidate,daemon_inspected=ack)
    assert mutation.recovery_status(tmp_path)==before
    receipt=mutation.acknowledge(tmp_path,ident,daemon_inspected=True)
    assert receipt["acknowledged"] and not receipt["daemon_idle_verified"]
    assert not receipt["automatic_retry_permitted"]
    with op.runtime_operation(tmp_path,"start") as lease:
        assert lease.current()


def test_process_crash_retains_compose_intent(tmp_path):
    from skeleton.app import runtime_mutation as mutation
    code=("from pathlib import Path; import os,sys;"
          "from skeleton.app.runtime_operation import runtime_operation;"
          "from skeleton.app.runtime_mutation import begin;"
          "lease=runtime_operation(Path(sys.argv[1]),'start');"
          "begin(lease.__enter__(),'compose-start');os._exit(43)")
    done=subprocess.run([sys.executable,"-c",code,str(tmp_path)],
        cwd=Path(__file__).resolve().parents[2],timeout=20)
    assert done.returncode==43
    assert mutation.recovery_status(tmp_path)["mutation"]=="compose-start"
    with pytest.raises(op.RuntimeOperationDenied,match="previous runtime mutation"):
        with op.runtime_operation(tmp_path,"stop"):
            pytest.fail("dead process falsely cleared mutation")


@pytest.mark.parametrize("payload",[b"",b"{}",b"x"*1025,b'{"schema":"bad"}'])
def test_malformed_intent_is_never_removed_automatically(tmp_path,payload):
    from skeleton.app import runtime_mutation as mutation
    path=tmp_path/mutation.PENDING_NAME
    path.write_bytes(payload)
    path.chmod(0o600)
    with pytest.raises(op.RuntimeOperationDenied):
        mutation.recovery_status(tmp_path)
    with pytest.raises(op.RuntimeOperationDenied):
        mutation.acknowledge(tmp_path,"a"*32,daemon_inspected=True)
    assert path.read_bytes()==payload


def test_intent_contains_no_command_arguments_or_secrets(tmp_path):
    from types import SimpleNamespace
    from skeleton.app import runtime_mutation as mutation
    private="fixture-private-token-not-for-storage"
    with op.runtime_operation(tmp_path,"stop") as lease:
        def runner(command,env):
            raw=(tmp_path/mutation.PENDING_NAME).read_bytes()
            assert private.encode() not in raw and b"JWT_SECRET" not in raw
            return SimpleNamespace(returncode=0)
        mutation.run_mutation(lease,"compose-stop",runner,["docker",private],env={"JWT_SECRET":private})


def test_wrong_mutation_scope_never_dispatches(tmp_path):
    from skeleton.app import runtime_mutation as mutation
    with op.runtime_operation(tmp_path,"setup") as lease:
        with pytest.raises(op.RuntimeOperationDenied):
            mutation.run_mutation(lease,"compose-start",lambda:pytest.fail("setup ran Docker"))
        assert mutation.pending(lease) is None
