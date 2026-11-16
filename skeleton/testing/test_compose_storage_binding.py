"""Resolved project/storage admission against bounded Docker fixture outputs."""
from copy import deepcopy
import json
import subprocess

import pytest

from skeleton.app import compose_storage_binding as binding

PROJECT="fixture"
COMMAND=("docker","compose","-f","docker-compose.yml","--env-file",".env",
         "up","-d","mongo","skeleton","backend","frontend")


def model():
    return {"name":PROJECT,
            "volumes":{role:{"name":PROJECT+"_"+role,"driver":"local"}
                       for role in binding.VOLUME_ROLES},
            "services":{role:{"container_name":"tutolage-"+role,
                "volumes":[{"type":"volume","source":volume,"target":target}
                           for target,volume in binding._BINDINGS.get(role,{}).items()]}
                        for role in binding.CONTAINER_ROLES}}


def fixture_runner(*, resolved=None, volumes=(), containers=(), container_override=None,
                   volume_override=None, fail_on=None, drift=False, changed_model=False):
    payload=model() if resolved is None else resolved
    calls=[]
    def runner(command,**kw):
        calls.append(tuple(command))
        assert kw["stderr"]==kw["stdin"]==subprocess.DEVNULL
        assert kw["check"] is False
        assert kw["env"]=={"DOCKER_CONTEXT":"fixture-context"}
        if fail_on and fail_on in command:
            return subprocess.CompletedProcess(command,1)
        if command[1]=="compose":
            assert tuple(command)==COMMAND[:6]+("config","--format","json")
            value=deepcopy(payload)
            if changed_model and sum(c[1]=="compose" for c in calls)>1:
                value["name"]="changed"
            raw=json.dumps(value).encode()
        elif command[1:3]==["volume","ls"]:
            names=volumes
            if "--filter" in command:
                role=command[command.index("--filter")+1].split("=")[-1]
                names=[v for v in names if v.endswith("_"+role)]
            elif drift and sum(c[1:3]==("volume","ls") and "--filter" not in c for c in calls)>1:
                names=(*names,"new_volume")
            raw=b"".join(n.encode()+b"\n" for n in names)
        elif command[1]=="ps":
            raw=b"".join(n.encode()+b"\n" for n in containers)
        elif command[1:3]==["volume","inspect"]:
            role=command[-1][len(PROJECT)+1:]
            value={"project":PROJECT,"role":role,"driver":"local","scope":"local"}
            if volume_override:
                value.update(volume_override)
            raw=json.dumps(value).encode()
        elif command[1:3]==["container","inspect"]:
            role=command[-1].removeprefix("tutolage-")
            value={"project":PROJECT,"service":role,
                   "mounts":[{"Type":"volume","Name":PROJECT+"_"+volume,"Destination":path,"RW":True}
                             for path,volume in binding._BINDINGS.get(role,{}).items()]}
            if container_override:
                value.update(container_override)
            raw=json.dumps(value).encode()
        else:
            pytest.fail("unexpected Docker action")
        kw["stdout"].write(raw)
        return subprocess.CompletedProcess(command,0)
    return runner,calls


def observe(root,runner,admit=None):
    return binding.observe_binding(root,command=COMMAND,environ={"DOCKER_CONTEXT":"fixture-context"},
                                   runner=runner,admit=admit)


def test_empty_project_and_existing_matched_project_both_admitted(tmp_path):
    for volumes,containers in [((),()),(tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
                     tuple("tutolage-"+r for r in binding.CONTAINER_ROLES))]:
        runner,calls=fixture_runner(volumes=volumes,containers=containers)
        report=observe(tmp_path,runner)
        assert report.admitted and report.code=="binding_observed"
        assert report.existing_containers==len(containers)
        assert report.existing_volumes==len(volumes)
        assert report.to_dict()["storage_modified"] is False
        assert report.to_dict()["database_authenticated"] is False
        assert not any("up" in call or "rm" in call for call in calls)


@pytest.mark.parametrize("mutation",["project","name","external","driver","driver_opts",
                                      "mount_type","mount_role","readonly","alias","duplicate","parent"])
def test_resolved_config_denies_authority_substitution(tmp_path,mutation):
    value=model()
    volume=value["volumes"]["mongo_data"]
    mounts=value["services"]["mongo"]["volumes"]
    if mutation=="project":
        value["name"]="invalid space"
    elif mutation=="name":
        volume["name"]="alternate"
    elif mutation=="external":
        volume["external"]=True
    elif mutation=="driver":
        volume["driver"]="remote"
    elif mutation=="driver_opts":
        volume["driver_opts"]={"device":"elsewhere"}
    elif mutation=="mount_type":
        mounts[0]["type"]="bind"
    elif mutation=="mount_role":
        mounts[0]["source"]="backend_data"
    elif mutation=="readonly":
        mounts[0]["read_only"]=True
    elif mutation=="alias":
        value["services"]["frontend"]["volumes"]=[{"type":"volume","source":"mongo_data","target":"/elsewhere"}]
    elif mutation=="duplicate":
        mounts.append(dict(mounts[0]))
    else:
        mounts.append({"type":"bind","target":"/data","source":"elsewhere"})
    runner,calls=fixture_runner(resolved=value)
    assert not observe(tmp_path,runner).admitted
    assert len(calls)==1


@pytest.mark.parametrize("role",binding.VOLUME_ROLES)
def test_alternate_project_volume_blocks_empty_replacement(tmp_path,role):
    runner,_=fixture_runner(volumes=("old_project_"+role,))
    report=observe(tmp_path,runner)
    assert not report.admitted and report.code=="alternate_persistent_volume_detected"


@pytest.mark.parametrize("override",[
    {"project":"foreign"},{"role":"backend_data"},{"driver":"nfs"},{"scope":"global"},
])
def test_volume_ownership_is_not_inferred_from_name(tmp_path,override):
    runner,_=fixture_runner(volumes=(PROJECT+"_mongo_data",),volume_override=override)
    assert observe(tmp_path,runner).code=="existing_volume_ownership_mismatch"


@pytest.mark.parametrize("override",[
    {"project":"foreign"},{"service":"backend"},{"mounts":[]},
    {"mounts":[{"Type":"bind","Destination":"/data/db","RW":True}]},
])
def test_existing_container_project_and_mounts_must_match(tmp_path,override):
    runner,_=fixture_runner(containers=("tutolage-mongo",),container_override=override)
    assert not observe(tmp_path,runner).admitted


@pytest.mark.parametrize("kwargs",[{"drift":True},{"changed_model":True},{"fail_on":"ps"}])
def test_inventory_or_render_drift_prevents_admission(tmp_path,kwargs):
    runner,_=fixture_runner(**kwargs)
    assert not observe(tmp_path,runner).admitted


def test_epoch_rejection_stops_before_further_docker_reads(tmp_path):
    runner,calls=fixture_runner()
    def admit():
        return not calls
    assert observe(tmp_path,runner,admit).code=="runtime_epoch_changed"
    assert len(calls)==1


@pytest.mark.parametrize("raw",[b"{}",b'{"name":"a","name":"b"}',b"x"*2097153,b"\xff"])
def test_malformed_render_never_admits_start(tmp_path,raw):
    def runner(command,**kw):
        kw["stdout"].write(raw)
        return subprocess.CompletedProcess(command,0)
    assert not observe(tmp_path,runner).admitted


def test_installer_integration_denies_mutation_before_start(tmp_path,monkeypatch):
    from skeleton.app import installer
    from skeleton.app.setup_runtime import SetupResult
    from skeleton.app.preloader import PreloadReport,PreloadCheck
    config=tmp_path/".env"
    config.write_text("FRONTEND_PORT=3000\n")
    monkeypatch.setattr(installer,"inspect_host",lambda *a,**k:PreloadReport(
        tmp_path,"fixture","3.11",(PreloadCheck("host:ready",True,"ready"),)))
    monkeypatch.setattr(installer,"ensure_runtime_environment",lambda *a,**k:SetupResult(
        config,False,False,(),(),()))
    monkeypatch.setattr(installer,"preflight",lambda *a,**k:())
    monkeypatch.setattr(installer,"checks_ok",lambda *a,**k:True)
    calls=[]
    def runner(command,**kw):
        calls.append(command)
        assert "up" not in command
        if "--format" in command:
            value=model()
            value["volumes"]["mongo_data"]["name"]="alternate"
            kw["stdout"].write(json.dumps(value).encode())
        return subprocess.CompletedProcess(command,0)
    receipt=installer.install_application(tmp_path,start=True,install_python=False,runner=runner)
    assert not receipt.ok and receipt.phases[-1].name=="start"
    assert "compose_volume_identity_mismatch" in receipt.phases[-1].detail
    assert len(calls)==2
