"""Storage observation contracts: no Docker daemon or database writes in tests."""
from __future__ import annotations
import subprocess
import pytest
from skeleton.app import storage_custody as custody


def fake_runner(*, volumes=(), containers=(), labels=None, fail_at=None, mutate=False):
    labels=labels or {}
    calls=[]
    def run(command,**kw):
        calls.append(tuple(command))
        assert command[1] in {"volume","ps"}
        assert kw["stdin"]==kw["stderr"]==subprocess.DEVNULL
        assert kw["timeout"]==15
        assert kw["check"] is False
        if fail_at==len(calls):
            return subprocess.CompletedProcess(command,1)
        if command[1]=="ps":
            names=containers
        elif "--filter" in command:
            role=command[command.index("--filter")+1].split("=")[-1]
            names=labels.get(role,())
        else:
            names=volumes
            if mutate and len(calls)>1:
                names=(*volumes,"appeared_mongo_data")
        for name in names:
            kw["stdout"].write(name.encode("ascii")+b"\n")
        return subprocess.CompletedProcess(command,0)
    return run,calls


def test_empty_selected_daemon_allows_initial_credential_identity(tmp_path):
    runner,calls=fake_runner(volumes=("unrelated-volume",),containers=("unrelated",))
    report=custody.observe_storage(tmp_path,runner=runner,environ={"DOCKER_CONTEXT":"local"})
    assert report.new_credentials_permitted
    assert len(calls)==9
    assert report.to_dict()["database_authenticated"] is False
    assert "unrelated" not in repr(report.to_dict())


@pytest.mark.parametrize("role",custody.VOLUME_ROLES)
@pytest.mark.parametrize("legacy",[True,False])
def test_existing_canonical_volume_blocks_credential_generation(tmp_path,role,legacy):
    name="old_project_"+role if legacy else "custom-private-name"
    runner,_=fake_runner(volumes=(name,),labels={} if legacy else {role:(name,)})
    report=custody.observe_storage(tmp_path,runner=runner)
    assert report.observed and report.volume_roles==(role,)
    assert not report.new_credentials_permitted
    assert name not in repr(report.to_dict())
    with pytest.raises(custody.StorageCustodyDenied):
        custody.require_new_storage_identity(tmp_path,runner=runner)


@pytest.mark.parametrize("role",custody.CONTAINER_ROLES)
def test_stopped_or_running_canonical_container_blocks_new_identity(tmp_path,role):
    runner,_=fake_runner(containers=("tutolage-"+role,))
    report=custody.observe_storage(tmp_path,runner=runner)
    assert report.container_roles==(role,) and not report.new_credentials_permitted


@pytest.mark.parametrize("position",range(1,10))
def test_any_failed_docker_observation_denies_initial_identity(tmp_path,position):
    runner,_=fake_runner(fail_at=position)
    assert not custody.observe_storage(tmp_path,runner=runner).observed


def test_inventory_drift_and_unlisted_label_denied(tmp_path):
    runner,_=fake_runner(mutate=True)
    assert not custody.observe_storage(tmp_path,runner=runner).observed
    runner,_=fake_runner(labels={"mongo_data":("newly-appeared",)})
    assert not custody.observe_storage(tmp_path,runner=runner).observed


@pytest.mark.parametrize("raw",[b"truncated",b"duplicate\nduplicate\n",b"bad name\n",
                                b"x"*1048577,b"not-a-name\x00\n"])
def test_malformed_inventory_not_observed(tmp_path,raw):
    def runner(command,**kw):
        kw["stdout"].write(raw)
        return subprocess.CompletedProcess(command,0)
    report=custody.observe_storage(tmp_path,runner=runner)
    assert not report.observed and not report.new_credentials_permitted


def test_observation_pins_process_environment_and_does_not_report_context(tmp_path):
    source={"DOCKER_CONTEXT":"operator-private-context"}
    calls=[]
    def runner(command,**kw):
        calls.append(kw["env"]["DOCKER_CONTEXT"])
        source["DOCKER_CONTEXT"]="unexpected-context"
        return subprocess.CompletedProcess(command,0)
    report=custody.observe_storage(tmp_path,runner=runner,environ=source)
    assert report.new_credentials_permitted
    assert calls==["operator-private-context"]*9
    assert "operator-private-context" not in repr(report.to_dict())
