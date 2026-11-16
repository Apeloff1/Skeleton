"""Shutdown receipt test fixtures exercise the real observation and dispatch logic."""
import json
import subprocess

import pytest

from skeleton.app import compose_stop_custody as stop
from skeleton.app.assembly import compose_command
from skeleton.app.runtime_operation import runtime_operation

CMD=compose_command("down",install_env=True)
ENV={"COMPOSE_PROJECT_NAME":"fixture","COMPOSE_REMOVE_ORPHANS":"1"}


def daemon_fixture(fault=None):
    calls=[]
    state={"stopped":False}
    names=("tutolage-backend","tutolage-mongo")
    def runner(command,**kw):
        calls.append(tuple(command))
        assert kw["stderr"]==kw["stdin"]==subprocess.DEVNULL
        assert kw["env"]["COMPOSE_REMOVE_ORPHANS"]=="0"
        if command[-1]=="stop":
            assert tuple(command)==CMD
            state["stopped"]=True
            if fault=="timeout":
                raise subprocess.TimeoutExpired(command,90)
            if fault=="exit":
                return subprocess.CompletedProcess(command,5)
            return subprocess.CompletedProcess(command,0)
        if command[1]=="info":
            value={"id":"other-daemon" if fault=="daemon" and state["stopped"] else "fixture-daemon"}
        elif command[1]=="compose":
            value={"name":"foreign" if fault=="project" and state["stopped"] else "fixture",
                   "services":{role:{"container_name":"tutolage-"+role} for role in stop.CONTAINER_ROLES}}
            if fault=="extra_service":
                value["services"]["foreign"]={"container_name":"foreign"}
        elif command[1] in ("ps","volume"):
            if command[1]=="volume":
                selected=() if fault=="volume_removed" and state["stopped"] else ("fixture_mongo_data",)
            elif fault=="foreign" and "--filter" in command:
                selected=()
            elif fault=="orphan":
                selected=(*names,"foreign")
            elif fault=="removed" and state["stopped"]:
                selected=names[:-1]
            elif fault=="empty":
                selected=()
            else:
                selected=names
            kw["stdout"].write(b"".join(name.encode()+b"\n" for name in selected))
            return subprocess.CompletedProcess(command,0)
        elif command[1:3]==["container","inspect"]:
            name=command[-1]
            running=not state["stopped"] or fault=="still_running"
            value={"id":("c" if state["stopped"] and fault=="recreated" else "a" if name.endswith("mongo") else "b")*64,
                   "project":"fixture","service":name.removeprefix("tutolage-"),
                   "running":running,"status":"running" if running else "exited"}
        else:
            pytest.fail("unreviewed Docker action")
        kw["stdout"].write(json.dumps(value).encode())
        return subprocess.CompletedProcess(command,0)
    return runner,calls


@pytest.mark.parametrize("fault",[None,"empty","foreign","orphan","extra_service","timeout","exit",
                                  "daemon","project","volume_removed","removed","recreated","still_running"])
def test_shutdown_is_owned_non_destructive_and_reobserved(tmp_path,fault):
    (tmp_path/".env").write_text("FRONTEND_PORT=3000\n")
    runner,calls=daemon_fixture(fault)
    with runtime_operation(tmp_path,"stop") as lease:
        report=stop.stop_owned_runtime(tmp_path,command=CMD,environ=ENV,runner=runner,lease=lease)
    assert report.ok is (fault in (None,"empty"))
    assert not any("rm" in c or "down" in c or "--remove-orphans" in c for c in calls)
    assert sum(c[-1]=="stop" for c in calls)==(0 if fault in {"empty","foreign","orphan","extra_service"} else 1)
    assert "fixture-daemon" not in repr(report)
    if fault=="timeout":
        from skeleton.app.runtime_mutation import recovery_status
        assert recovery_status(tmp_path)["pending"] is True


def test_shutdown_command_cannot_be_replaced_by_removal(tmp_path):
    (tmp_path/".env").write_text("FRONTEND_PORT=3000\n")
    with runtime_operation(tmp_path,"stop") as lease:
        report=stop.stop_owned_runtime(tmp_path,command=(*CMD[:-1],"down","-v"),environ=ENV,
            runner=lambda *a,**k:pytest.fail("unadmitted shutdown"),lease=lease)
    assert not report.ok
