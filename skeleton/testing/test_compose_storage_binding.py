"""Resolved project/storage admission against bounded Docker fixture outputs."""
from copy import deepcopy
import json
import subprocess

import pytest

from skeleton.app import compose_storage_binding as binding
from skeleton.app import compose_runtime_identity as runtime
from skeleton.app import compose_security_contract as isolation
from skeleton.testing.compose_wiring_fixtures import fixture_values, populate_wiring

PROJECT="fixture"
COMMAND=("docker","compose","-f","docker-compose.yml","--env-file",".env",
         "up","-d","mongo","skeleton","backend","frontend")


def model():
    value = {"name":PROJECT,"networks":{"tutolage":{"name":PROJECT+"_tutolage","driver":"bridge"}},
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
        spec["networks"]={"tutolage":None}
        if role in ("backend","skeleton"):
            spec.update(read_only=True,cap_drop=["ALL"],security_opt=["no-new-privileges:true"],
                        tmpfs=["/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777"])
        if role=="skeleton":
            from pathlib import Path
            spec["volumes"].append({"type":"bind","source":str(Path.cwd().resolve()/"data"/"local-ai"),
                                    "target":"/app/local-ai","read_only":True})
        if role in ("mongo","chroma"):
            spec["image"]=role+":"+ "fixture@sha256:"+"b"*64
    return value


def fixture_runner(*, resolved=None, volumes=(), containers=(), container_override=None,
                   volume_override=None, fail_on=None, drift=False, changed_model=False,
                   daemon="fixture-daemon", container_running=True, created="2026-01-01T12:00:00Z",
                   image_tag_mismatch=False, model_env_drift=False, network_override=None,
                   isolation_override=None, health="healthy"):
    payload=model() if resolved is None else resolved
    calls=[]
    def runner(command,**kw):
        calls.append(tuple(command))
        assert kw["stderr"]==kw["stdin"]==subprocess.DEVNULL
        assert kw["check"] is False
        assert kw["env"]==fixture_values()
        if fail_on and fail_on in command:
            return subprocess.CompletedProcess(command,1)
        if command[1]=="info":
            raw=json.dumps({"id":daemon}).encode()
        elif command[1]=="compose":
            assert tuple(command)==COMMAND[:6]+("config","--format","json")
            value=deepcopy(payload)
            populate_wiring(value,kw["cwd"],fixture_values())
            if changed_model and sum(c[1]=="compose" for c in calls)>1:
                value["name"]="changed"
            if model_env_drift and sum(c[1]=="compose" for c in calls)>1:
                value["services"]["backend"]["environment"]["PRIVATE_FIXTURE"]="different"
            raw=json.dumps(value).encode()
        elif command[1:3]==["network","inspect"]:
            network={"id":"e"*64,"name":PROJECT+"_tutolage","project":PROJECT,
                     "role":"tutolage","driver":"bridge","scope":"local","ingress":False}
            network.update(network_override or {})
            raw=json.dumps(network).encode()
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
            for mount in payload["services"][role].get("volumes",[]):
                if mount.get("type")=="bind":
                    value["mounts"].append({"Type":"bind","Destination":mount["target"],
                                            "RW":not mount.get("read_only",False)})
            _,published,target=runtime.HOST_DEFAULTS[role]
            value.update(image_id="sha256:"+"d"*64,
                         started_at="2026-01-01T12:00:00.000000000Z",restart_count=0,
                         image_ref=payload["services"][role].get("image",PROJECT+"-"+role),
                         ports={str(target)+"/tcp":[{"HostIp":"127.0.0.1","HostPort":str(published)}]})
            protected=role in ("backend","skeleton")
            spec={"privileged":False,"pid_mode":"","ipc_mode":"private","uts_mode":"",
                  "cap_add":None,"devices":[],"device_requests":None,"device_cgroup_rules":None,
                  "network_mode":PROJECT+"_tutolage","networks":[PROJECT+"_tutolage"],
                  "read_only":protected,"cap_drop":["ALL"] if protected else None,
                  "security_opt":["no-new-privileges=true"] if protected else None,
                  "user":"appuser" if protected else "",
                  "tmpfs":{"/tmp":"rw,noexec,nosuid,nodev,size=67108864,mode=1777"} if protected else None}
            spec.update(isolation_override or {})
            value.update(isolation=spec,health=health)
            if container_override:
                value.update(container_override)
            raw=json.dumps(value).encode()
        else:
            pytest.fail("unexpected Docker action")
        kw["stdout"].write(raw)
        return subprocess.CompletedProcess(command,0)
    return runner,calls


def observe(root,runner,admit=None,**options):
    return binding.observe_binding(root,command=COMMAND,environ=fixture_values(),
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



@pytest.mark.parametrize("suffix,expected", [
    (("up","-d","--no-deps","frontend"),True),
    (("up","-d","frontend"),False),
    (("up","-d","--no-deps","backend"),False),
    (("up","-d","--no-deps","frontend","mongo"),False),
    (("up","-d","--no-deps","--force-recreate","frontend"),False),
])
def test_recovery_command_scope_matches_original_render(suffix,expected):
    assert binding.recovery_render_matches(COMMAND,COMMAND[:6]+suffix) is expected


@pytest.mark.parametrize("fault",["none","daemon","removed_volume","new_model"])
def test_recovery_preflight_rebinds_failed_start_to_original_authority(tmp_path,fault):
    original,_=fixture_runner(volumes=(PROJECT+"_mongo_data",))
    before=observe(tmp_path,original)
    assert before.admitted
    opts={"volumes":(PROJECT+"_mongo_data",PROJECT+"_backend_data")}
    if fault=="daemon":
        opts["daemon"]="other-daemon"
    elif fault=="removed_volume":
        opts["volumes"]=()
    elif fault=="new_model":
        value=model()
        value["services"]["backend"]["environment"]={"FIXTURE":"not-original"}
        opts["resolved"]=value
    after,_=fixture_runner(**opts)
    result=observe(tmp_path,after,previous=before)
    assert result.admitted is (fault=="none")


def test_frontend_recovery_requires_only_frontend_but_never_certifies_full_stack(tmp_path):
    before,_=fixture_runner(volumes=(PROJECT+"_mongo_data",))
    first=observe(tmp_path,before)
    after,_=fixture_runner(volumes=(PROJECT+"_mongo_data",),containers=("tutolage-frontend",))
    result=observe(tmp_path,after,previous=first,require_frontend=True)
    assert result.admitted
    assert tuple(dict(result.identity.active_runtime_digests))==("frontend",)
    assert not observe(tmp_path,after,previous=first,require_started=True).admitted


@pytest.mark.parametrize("override",[
    {"id":"b"*64},{"restart_count":1},{"started_at":"2026-02-01T12:00:00Z"},
])
def test_setup_recovery_availability_cannot_inherit_stale_frontend_probe(tmp_path,override):
    before,_=fixture_runner()
    first=observe(tmp_path,before)
    after,_=fixture_runner(containers=("tutolage-frontend",))
    recovered=observe(tmp_path,after,previous=first,require_frontend=True)
    assert recovered.admitted
    changed,_=fixture_runner(containers=("tutolage-frontend",),container_override=override)
    final=observe(tmp_path,changed,previous=recovered,require_frontend=True,require_same_runtime=True)
    assert final.code=="runtime_epoch_changed_during_qualification"


def test_frontend_recovery_never_accepts_other_compose_project_prefix():
    recovery=("docker","compose","-f","docker-compose.yml","-p","other",
              "--env-file",".env","up","-d","--no-deps","frontend")
    assert not binding.recovery_render_matches(COMMAND,recovery)



@pytest.mark.parametrize("fault",[
    "privileged","host_pid","host_network","device","capability","rw_root","missing_nnp",
    "tmpfs_exec","tmpfs_unbounded","root_user","socket","foreign_network","wrong_driver",
])
def test_model_security_denies_unreviewed_host_authority(tmp_path,fault):
    config=model()
    backend=config["services"]["backend"]
    if fault=="privileged":
        backend["privileged"]=True
    elif fault=="host_pid":
        backend["pid"]="host"
    elif fault=="host_network":
        backend["network_mode"]="host"
    elif fault=="device":
        backend["devices"]=["/dev/sda"]
    elif fault=="capability":
        backend["cap_add"]=["SYS_ADMIN"]
    elif fault=="rw_root":
        backend["read_only"]=False
    elif fault=="missing_nnp":
        backend["security_opt"]=[]
    elif fault=="tmpfs_exec":
        backend["tmpfs"]=["/tmp:rw,exec,nosuid,nodev,size=64m"]
    elif fault=="tmpfs_unbounded":
        backend["tmpfs"]=["/tmp:rw,noexec,nosuid,nodev"]
    elif fault=="root_user":
        backend["user"]="0"
    elif fault=="socket":
        backend["volumes"].append({"type":"bind","source":"/var/run/docker.sock",
                                   "target":"/var/run/docker.sock","read_only":False})
    elif fault=="foreign_network":
        backend["networks"]={"other":None}
    else:
        config["networks"]["tutolage"]["driver"]="host"
    runner,_=fixture_runner(resolved=config)
    assert not observe(tmp_path,runner).admitted


@pytest.mark.parametrize("override",[
    {"privileged":True},{"pid_mode":"host"},{"ipc_mode":"host"},{"cap_add":["SYS_ADMIN"]},
    {"devices":[{}]},{"networks":["foreign"]},{"network_mode":"host"},{"read_only":False},
    {"user":"root"},{"security_opt":[]},{"tmpfs":{"/tmp":"rw,size=64m"}},
])
def test_actual_isolation_not_inferred_from_rendered_config(tmp_path,override):
    before,_=fixture_runner()
    first=observe(tmp_path,before)
    assert first.admitted
    runner,_=fixture_runner(volumes=tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
        containers=tuple("tutolage-"+r for r in binding._ACTIVE_ROLES),isolation_override=override)
    assert not observe(tmp_path,runner,previous=first,require_started=True).admitted


@pytest.mark.parametrize("override",[
    {"driver":"host"},{"project":"foreign"},{"scope":"global"},{"ingress":True},
])
def test_running_network_must_be_owned_local_bridge(tmp_path,override):
    original,_=fixture_runner()
    first=observe(tmp_path,original)
    runner,_=fixture_runner(volumes=tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
        containers=tuple("tutolage-"+r for r in binding._ACTIVE_ROLES),network_override=override)
    assert observe(tmp_path,runner,previous=first,require_started=True).code=="runtime_bridge_ownership_unverified"


def test_replaced_bridge_or_unhealthy_daemon_invalidates_http_continuity(tmp_path):
    original,_=fixture_runner()
    first=observe(tmp_path,original)
    options={"volumes":tuple(PROJECT+"_"+r for r in binding.VOLUME_ROLES),
             "containers":tuple("tutolage-"+r for r in binding._ACTIVE_ROLES)}
    started,_=fixture_runner(**options,health="starting")
    post=observe(tmp_path,started,previous=first,require_started=True)
    assert post.admitted
    for change,code in [({"network_override":{"id":"f"*64}},"runtime_bridge_changed"),
                        ({"health":"unhealthy"},"runtime_daemon_health_unverified")]:
        runner,_=fixture_runner(**options,**change)
        final=observe(tmp_path,runner,previous=post,require_started=True,require_same_runtime=True)
        assert final.code==code
    runner,_=fixture_runner(**options)
    assert observe(tmp_path,runner,previous=post,require_started=True,require_same_runtime=True).admitted



@pytest.mark.parametrize("options",[
    "rw,noexec,exec,nosuid,nodev,size=64m",
    "rw,noexec,nosuid,nodev,suid,size=64m",
    "rw,noexec,nosuid,nodev,rw,size=64m",
    "rw,noexec,nosuid,nodev,size=64m,size=67108864",
])
def test_tmpfs_safety_flags_cannot_be_overridden_by_contradictory_options(options):
    with pytest.raises(runtime.RuntimeIdentityDenied):
        isolation._required_tmpfs(isolation._tmpfs_options(options))


@pytest.mark.parametrize("user",["","root","root:app","0","000","000:1000"])
def test_runtime_user_admission_denies_effective_root_spelling(user):
    assert not isolation._nonroot(user)


@pytest.mark.parametrize("user",["appuser","1000","1000:1000"])
def test_runtime_user_preserves_canonical_nonroot_identity(user):
    assert isolation._nonroot(user)


@pytest.mark.parametrize("security_opt",[["seccomp=unconfined"],["apparmor:unconfined"],
                                         ["label=disable"],["no-new-privileges:false"]])
def test_container_cannot_disable_default_security_profile(tmp_path,security_opt):
    config=model()
    config["services"]["frontend"]["security_opt"]=security_opt
    runner,_=fixture_runner(resolved=config)
    assert not observe(tmp_path,runner).admitted


@pytest.mark.parametrize("fault",["rw_model","missing_model","foreign_socket","extra_mount"])
def test_live_bind_destinations_and_permissions_match_model(tmp_path,fault):
    config=model()
    expected=isolation.model_security(config,root=tmp_path,hot=False)
    spec={"privileged":False,"pid_mode":"","ipc_mode":"private","uts_mode":"",
          "cap_add":None,"devices":[],"device_requests":None,"device_cgroup_rules":None,
          "network_mode":PROJECT+"_tutolage","networks":[PROJECT+"_tutolage"],
          "read_only":True,"cap_drop":["ALL"],"security_opt":["no-new-privileges:true"],
          "user":"appuser","tmpfs":{"/tmp":"rw,noexec,nosuid,nodev,size=64m"}}
    mounts=[{"Type":"bind","Destination":"/app/local-ai","RW":False}]
    assert isolation.live_security({"isolation":spec,"mounts":mounts},expected["skeleton"])
    if fault=="rw_model":
        mounts[0]["RW"]=True
    elif fault=="missing_model":
        mounts.clear()
    elif fault=="foreign_socket":
        mounts.append({"Type":"bind","Destination":"/var/run/docker.sock","RW":True})
    else:
        mounts.append({"Type":"bind","Destination":"/app/extra","RW":False})
    with pytest.raises(runtime.RuntimeIdentityDenied,match="runtime_host_bind_not_reviewed"):
        isolation.live_security({"isolation":spec,"mounts":mounts},expected["skeleton"])
