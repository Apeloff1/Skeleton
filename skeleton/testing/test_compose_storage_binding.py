"""Resolved project/storage admission against bounded Docker fixture outputs."""
from copy import deepcopy
import json
import subprocess

import pytest

from skeleton.app import compose_storage_binding as binding
from skeleton.app import compose_runtime_identity as runtime

PROJECT="fixture"
COMMAND=("docker","compose","-f","docker-compose.yml","--env-file",".env",
         "up","-d","mongo","skeleton","backend","frontend")


def model():
    value = {"name":PROJECT,
            "volumes":{role:{"name":PROJECT+"_"+role,"driver":"local"}
                       for role in binding.VOLUME_ROLES},
            "services":{role:{"container_name":"tutolage-"+role,
                "volumes":[{"type":"volume","source":volume,"target":target}
                           for target,volume in binding._BINDINGS.get(role,{}).items()]}
                        for role in binding.CONTAINER_ROLES}}
    for role,spec in value["services"].items():
        _,published,target=runtime.HOST_DEFAULTS[role]
        spec["ports"]=[{"host_ip":"127.0.0.1","target":target,
                        "published":str(published),"protocol":"tcp"}]
        if role in ("mongo","chroma"):
            spec["image"]=role+":"+ "fixture@sha256:"+"b"*64
    return value


def fixture_runner(*, resolved=None, volumes=(), containers=(), container_override=None,
                   volume_override=None, fail_on=None, drift=False, changed_model=False,
                   daemon="fixture-daemon", container_running=True, created="2026-01-01T12:00:00Z",
                   image_tag_mismatch=False, model_env_drift=False):
    payload=model() if resolved is None else resolved
    calls=[]
    def runner(command,**kw):
        calls.append(tuple(command))
        assert kw["stderr"]==kw["stdin"]==subprocess.DEVNULL
        assert kw["check"] is False
        assert kw["env"]=={"DOCKER_CONTEXT":"fixture-context"}
        if fail_on and fail_on in command:
            return subprocess.CompletedProcess(command,1)
        if command[1]=="info":
            raw=json.dumps({"id":daemon}).encode()
        elif command[1]=="compose":
            assert tuple(command)==COMMAND[:6]+("config","--format","json")
            value=deepcopy(payload)
            if changed_model and sum(c[1]=="compose" for c in calls)>1:
                value["name"]="changed"
            if model_env_drift and sum(c[1]=="compose" for c in calls)>1:
                value["services"]["backend"]["environment"]={"PRIVATE_FIXTURE":"different"}
            raw=json.dumps(value).encode()
        elif command[1:3]==["image","inspect"]:
            raw=json.dumps({"id":"sha256:"+("c" if image_tag_mismatch else "d")*64}).encode()
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
            value={"project":PROJECT,"role":role,"driver":"local","scope":"local",
                   "created":created,"options":None}
            if volume_override:
                value.update(volume_override)
            raw=json.dumps(value).encode()
        elif command[1:3]==["container","inspect"]:
            role=command[-1].removeprefix("tutolage-")
            value={"project":PROJECT,"service":role,"id":"a"*64,"running":container_running,
                   "mounts":[{"Type":"volume","Name":PROJECT+"_"+volume,"Destination":path,"RW":True}
                             for path,volume in binding._BINDINGS.get(role,{}).items()]}
            _,published,target=runtime.HOST_DEFAULTS[role]
            value.update(image_id="sha256:"+"d"*64,
                         started_at="2026-01-01T12:00:00.000000000Z",restart_count=0,
                         image_ref=payload["services"][role].get("image",PROJECT+"-"+role),
                         ports={str(target)+"/tcp":[{"HostIp":"127.0.0.1","HostPort":str(published)}]})
            if container_override:
                value.update(container_override)
            raw=json.dumps(value).encode()
        else:
            pytest.fail("unexpected Docker action")
        kw["stdout"].write(raw)
        return subprocess.CompletedProcess(command,0)
    return runner,calls


def observe(root,runner,admit=None,**options):
    return binding.observe_binding(root,command=COMMAND,environ={"DOCKER_CONTEXT":"fixture-context"},
                                   runner=runner,admit=admit,**options)


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
    assert len(calls)==2


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
        if command[1]=="info":
            kw["stdout"].write(json.dumps({"id":"fixture-daemon"}).encode())
        elif "--format" in command:
            value=model()
            value["volumes"]["mongo_data"]["name"]="alternate"
            kw["stdout"].write(json.dumps(value).encode())
        return subprocess.CompletedProcess(command,0)
    receipt=installer.install_application(tmp_path,start=True,install_python=False,runner=runner)
    assert not receipt.ok and receipt.phases[-1].name=="start"
    assert "compose_volume_identity_mismatch" in receipt.phases[-1].detail
    assert len(calls)==3



@pytest.mark.parametrize("scenario",["healthy","missing","stopped","daemon_changed","volume_recreated"])
def test_post_start_requires_same_daemon_existing_volume_and_running_services(tmp_path,scenario):
    old_volumes=(PROJECT+"_mongo_data",)
    before,_=fixture_runner(volumes=old_volumes)
    previous=observe(tmp_path,before)
    assert previous.admitted
    volumes=tuple(PROJECT+"_"+role for role in binding.VOLUME_ROLES)
    containers=tuple("tutolage-"+role for role in binding._ACTIVE_ROLES)
    opts={}
    if scenario=="missing":
        containers=containers[:-1]
    elif scenario=="stopped":
        opts["container_running"]=False
    elif scenario=="daemon_changed":
        opts["daemon"]="other-daemon"
    elif scenario=="volume_recreated":
        opts["created"]="2026-02-01T12:00:00Z"
    after,_=fixture_runner(volumes=volumes,containers=containers,**opts)
    result=observe(tmp_path,after,previous=previous,require_started=True)
    assert result.admitted is (scenario=="healthy")
    assert "fixture-daemon" not in repr(result.to_dict())


def test_missing_prelaunch_receipt_cannot_certify_post_start(tmp_path):
    runner,_=fixture_runner()
    assert observe(tmp_path,runner,require_started=True).code=="prior_binding_unverified"


def test_volume_driver_options_deny_changed_storage_semantics(tmp_path):
    runner,_=fixture_runner(volumes=(PROJECT+"_mongo_data",),
                           volume_override={"options":{"device":"unreviewed"}})
    assert observe(tmp_path,runner).code=="existing_volume_driver_options_unqualified"


@pytest.mark.parametrize("case",["reviewed","production","writable","wrong_source","nested_override"])
def test_hot_overlay_preserves_only_reviewed_readonly_parent(tmp_path,case):
    value=model()
    mounts=value["services"]["backend"]["volumes"]
    mount={"type":"bind","source":str(tmp_path/"backend"),"target":"/app","read_only":True}
    mounts.append(mount)
    if case=="writable":
        mount["read_only"]=False
    elif case=="wrong_source":
        mount["source"]=str(tmp_path/"other")
    elif case=="nested_override":
        mounts.append({"type":"bind","source":str(tmp_path/"other"),"target":"/app/data/foreign"})
    if case=="reviewed":
        assert binding._resolved_model(value,root=tmp_path,hot=True)[0]==PROJECT
    else:
        with pytest.raises(binding.BindingDenied,match="compose_persistent_parent_mount"):
            binding._resolved_model(value,root=tmp_path,hot=case!="production")


@pytest.mark.parametrize("readonly",[True,False])
def test_existing_backend_hot_mount_does_not_disguise_writable_authority(tmp_path,readonly):
    value={"project":PROJECT,"service":"backend","id":"a"*64,"running":True,
           "mounts":[{"Type":"volume","Name":PROJECT+"_backend_data","Destination":"/app/data","RW":True},
                     {"Type":"bind","Destination":"/app","RW":not readonly}]}
    resolved={role:PROJECT+"_"+role for role in binding.VOLUME_ROLES}
    if readonly:
        assert len(binding._container_binding(value,PROJECT,"backend",resolved))==64
    else:
        with pytest.raises(binding.BindingDenied,match="existing_persistent_mount_shadowed"):
            binding._container_binding(value,PROJECT,"backend",resolved)



@pytest.mark.parametrize("fault",["wildcard","wrong_port","udp","extra","unpublished","range","unpinned"])
def test_runtime_model_rejects_unreviewed_ingress_or_base_image(tmp_path,fault):
    value=model()
    port=value["services"]["backend"]["ports"][0]
    if fault=="wildcard":
        port["host_ip"]="0.0.0.0"
    elif fault=="wrong_port":
        port["published"]="9000"
    elif fault=="udp":
        port["protocol"]="udp"
    elif fault=="extra":
        value["services"]["backend"]["ports"].append(dict(port,published="9000"))
    elif fault=="unpublished":
        port.pop("published")
    elif fault=="range":
        port["published"]="8001-8005"
    else:
        value["services"]["mongo"]["image"]="mongo:latest"
    runner,_=fixture_runner(resolved=value)
    assert not observe(tmp_path,runner).admitted


def test_full_resolved_model_drift_denies_even_unchanged_volume_mapping(tmp_path):
    runner,_=fixture_runner(model_env_drift=True)
    result=observe(tmp_path,runner)
    assert result.code=="compose_storage_model_changed"
    assert "PRIVATE_FIXTURE" not in repr(result)


@pytest.mark.parametrize("override",[
    {"image_ref":"foreign-image"}, {"image_id":"not-a-digest"},
    {"ports":{}}, {"ports":{"27017/tcp":[{"HostIp":"0.0.0.0","HostPort":"27017"}]}},
    {"ports":{"27017/udp":[{"HostIp":"127.0.0.1","HostPort":"27017"}]}},
])
def test_post_start_rejects_unqualified_actual_ingress_or_image(tmp_path,override):
    before,_=fixture_runner()
    previous=observe(tmp_path,before)
    assert previous.admitted
    after,_=fixture_runner(volumes=tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
        containers=tuple("tutolage-"+r for r in binding._ACTIVE_ROLES),
        container_override=override)
    result=observe(tmp_path,after,previous=previous,require_started=True)
    assert not result.admitted


def test_post_start_running_image_must_match_observed_local_tag(tmp_path):
    before,_=fixture_runner()
    previous=observe(tmp_path,before)
    after,_=fixture_runner(volumes=tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
        containers=tuple("tutolage-"+r for r in binding._ACTIVE_ROLES),image_tag_mismatch=True)
    assert observe(tmp_path,after,previous=previous,require_started=True).code=="running_image_tag_identity_mismatch"


def test_custom_production_ports_and_hot_ports_have_separate_exact_contract():
    value=model()
    value["services"]["frontend"]["ports"]=[{"host_ip":"127.0.0.1","target":8080,"published":"3300"}]
    expected=runtime.model_identity(value,values={"FRONTEND_PORT":"3300","FRONTEND_CONTAINER_PORT":"8080"},hot=False)
    assert expected["frontend"].ports==((8080,3300),)
    value["services"]["frontend"]["ports"].extend(
        {"host_ip":"127.0.0.1","target":p,"published":str(p)} for p in runtime._HOT)
    assert len(runtime.model_identity(value,values={"FRONTEND_PORT":"3300","FRONTEND_CONTAINER_PORT":"8080"},hot=True)["frontend"].ports)==5



@pytest.mark.parametrize("change",[
    {}, {"id":"f"*64}, {"restart_count":1}, {"started_at":"2026-01-01T12:01:00Z"},
])
def test_readiness_binds_active_container_epoch_across_observations(tmp_path,change):
    original,_=fixture_runner()
    before=observe(tmp_path,original)
    volumes=tuple(PROJECT+"_"+role for role in binding.VOLUME_ROLES)
    containers=tuple("tutolage-"+role for role in binding._ACTIVE_ROLES)
    started,_=fixture_runner(volumes=volumes,containers=containers)
    post=observe(tmp_path,started,previous=before,require_started=True)
    assert post.admitted
    last,_=fixture_runner(volumes=volumes,containers=containers,container_override=change)
    result=observe(tmp_path,last,previous=post,require_started=True,require_same_runtime=True)
    assert result.admitted is (not change)
    if change:
        assert result.code=="runtime_epoch_changed_during_qualification"


@pytest.mark.parametrize("override",[
    {"started_at":None},{"started_at":"0001-01-01T00:00:00Z"},
    {"restart_count":True},{"restart_count":-1},
])
def test_missing_or_invalid_runtime_epoch_is_not_qualified(tmp_path,override):
    before,_=fixture_runner()
    previous=observe(tmp_path,before)
    after,_=fixture_runner(volumes=tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
        containers=tuple("tutolage-"+r for r in binding._ACTIVE_ROLES),container_override=override)
    assert observe(tmp_path,after,previous=previous,require_started=True).code=="running_container_epoch_unverified"
