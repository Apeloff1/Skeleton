"""Source-archive, independent builder approval and live image binding regressions."""
from __future__ import annotations

import io
import importlib
import json
from pathlib import Path
import sys
import tarfile
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

SCRIPTS=Path(__file__).resolve().parents[2]/"scripts"
sys.path.insert(0,str(SCRIPTS))
q=importlib.import_module("qualify_first_install_images")
HEAD="a"*40
TOKEN="b"*32
ORIGINS={"backend":"http://127.0.0.1:8001","skeleton":"http://127.0.0.1:8010"}
PROJECT="skeleton"
NET="f"*64
FILES=("Dockerfile","backend/Dockerfile","frontend/Dockerfile",".dockerignore",
       "frontend/.dockerignore","pyproject.toml","backend/requirements.txt",
       "frontend/package.json","frontend/yarn.lock")


def receipt(**updates):
    row={"source_head":HEAD,"candidate":TOKEN,"archive":{"sha256":"1"*64,"bytes":100},
         "source_inventory":{"sha256":"2"*64,"files":9,"bytes":10},"origins":dict(ORIGINS),
         "images":[{"role":role,"tag":q._tag(HEAD,TOKEN,role),
                    "image_id":"sha256:"+str(i+3)*64,"os":"linux","architecture":"amd64"}
                   for i,role in enumerate(q.ROLES)],
         "build_mode":"isolated_tracked_git_archive_production","ambient_credentials_forwarded":False,
         "independent_builder_approved":False,"hermetic_reproducibility_qualified":False,
         "runtime_qualified":False,"release_qualified":False}
    row.update(updates)
    return q.canonical(q._receipt(q.BUILD_SCHEMA,row))+b"\n"


def approved(raw=None,**updates):
    raw=receipt() if raw is None else raw
    now=int(time.time())
    plan={"schema":q.PLAN_SCHEMA,"source_head":HEAD,"build_receipt_sha256":q.sha(raw),
          "authority_id":"reviewer","project":PROJECT,"review_evidence_sha256":"9"*64,
          "issued_at":now-1,"expires_at":now+600}
    plan.update(updates)
    secret=Ed25519PrivateKey.generate()
    key=secret.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    signature=secret.sign(q.DOMAIN+q.canonical(plan))
    return q.approve(raw,q.canonical(plan),signature,key,head=HEAD,authority="reviewer",project=PROJECT)


def test_build_receipt_and_review_are_separate():
    body=q.validate_build(receipt(),HEAD)
    assert not body["independent_builder_approved"]
    a=approved()
    assert a.plan["project"]==PROJECT
    assert a.receipt["runtime_qualified"] is False


@pytest.mark.parametrize("change",[
    {"release_qualified":True},{"runtime_qualified":True},{"source_head":"f"*40},
    {"ambient_credentials_forwarded":True},{"independent_builder_approved":True},
    {"hermetic_reproducibility_qualified":True},{"candidate":"bad"},
    {"archive":{"sha256":"bad","bytes":100}},{"images":[]},
    {"origins":{"backend":"http://example.com:8001","skeleton":"http://127.0.0.1:8010"}},
])
def test_scope_errors_denied(change):
    with pytest.raises(q.ImageQualificationDenied):
        q.validate_build(receipt(**change),HEAD)


@pytest.mark.parametrize("change",[
    {"build_receipt_sha256":"0"*64},{"project":"other"},{"authority_id":"other"},
    {"review_evidence_sha256":"0"*64},{"source_head":"f"*40},
    {"schema":"wrong"},{"expires_at":0},{"issued_at":0},
])
def test_signed_but_invalid_plan_denied(change):
    with pytest.raises(q.ImageQualificationDenied):
        approved(**change)


def test_changed_signature_denied():
    raw=receipt()
    now=int(time.time())
    plan={"schema":q.PLAN_SCHEMA,"source_head":HEAD,"build_receipt_sha256":q.sha(raw),
          "authority_id":"reviewer","project":PROJECT,"review_evidence_sha256":"9"*64,
          "issued_at":now-1,"expires_at":now+600}
    key=Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    with pytest.raises(q.ImageQualificationDenied):
        q.approve(raw,q.canonical(plan),b"x"*64,key,head=HEAD,authority="reviewer",project=PROJECT)


@pytest.mark.parametrize("value",[
    "http://127.0.0.1","http://127.0.0.1:80","http://localhost:8001/",
    "http://user@localhost:8001","http://localhost:8001?q=1",
    "http://localhost:8001#fragment","https://localhost:8001",
    "http://localhost:08001","http://127.0.0.2:8001","http://localhost:99999",
])
def test_reject_ambiguous_browser_origin(value):
    with pytest.raises(q.ImageQualificationDenied):
        q._origin(value)


@pytest.mark.parametrize("name",[
    "../escape","/absolute","a/../escape","a//b","a/./b","a\\b","x/.git/config",
    ".env","x/.ENV.local","x/.envrc","a/\x01b",
])
def test_archive_path_rejections(name):
    with pytest.raises(q.ImageQualificationDenied):
        q._relative(name)


def make_archive(path,extra=None):
    with tarfile.open(path,"w") as t:
        for file in FILES:
            raw=file.encode("ascii")
            info=tarfile.TarInfo(file)
            info.size=len(raw)
            info.mode=0o644
            t.addfile(info,io.BytesIO(raw))
        if extra is not None:
            info,raw=extra
            t.addfile(info,io.BytesIO(raw) if raw is not None else None)


def test_extraction_and_running_inventory_detect_content_mode_and_extra_file(tmp_path):
    archive=tmp_path/"source.tar"
    make_archive(archive)
    root=tmp_path/"context"
    original=q._extract(archive,root)
    assert original==q._inventory(root)
    assert original["files"]==len(FILES)
    file=root/"Dockerfile"
    file.chmod(0o600)
    file.write_text("mutated")
    assert original!=q._inventory(root)


@pytest.mark.parametrize("kind",[tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.FIFOTYPE,tarfile.CHRTYPE])
def test_archive_link_and_special_members_denied(tmp_path,kind):
    archive=tmp_path/"source.tar"
    info=tarfile.TarInfo("unsafe")
    info.type=kind
    info.linkname="../outside"
    make_archive(archive,(info,None))
    with pytest.raises(q.ImageQualificationDenied):
        q._extract(archive,tmp_path/"context")


def test_duplicate_member_rejected(tmp_path):
    archive=tmp_path/"source.tar"
    info=tarfile.TarInfo("Dockerfile")
    info.size=1
    make_archive(archive,(info,b"x"))
    with pytest.raises(q.ImageQualificationDenied):
        q._extract(archive,tmp_path/"context")


def test_build_arguments_are_isolated_production_and_never_service_tag(tmp_path):
    for role in q.ROLES:
        args=q._build_args(role,tmp_path,HEAD,TOKEN,"1"*64,"2"*64,ORIGINS,tmp_path/"iid")
        assert args[0]=="build"
        assert args[args.index("--tag")+1]==q._tag(HEAD,TOKEN,role)
        assert "--secret" not in args and "--ssh" not in args and "--privileged" not in args
        if role in ("backend","frontend"):
            assert args[args.index("--target")+1]=="production"
        if role=="frontend":
            assert "EXPO_PUBLIC_BACKEND_URL="+ORIGINS["backend"] in args
            assert "EXPO_PUBLIC_SKELETON_URL="+ORIGINS["skeleton"] in args


def test_prepare_writes_only_candidate_override(monkeypatch,tmp_path):
    tmp_path.chmod(0o700)
    monkeypatch.setattr(q,"_assert_source",lambda *args:None)
    monkeypatch.setattr(q,"_verify_images",lambda *args:None)
    result=q.prepare(approved(),tmp_path/"override.json",8080)
    overlay=json.loads((tmp_path/"override.json").read_bytes())
    assert set(overlay)=={"services"} and set(overlay["services"])==set(q.ROLES)
    assert all(overlay["services"][role]=={"image":q._tag(HEAD,TOKEN,role),"pull_policy":"never"}
               for role in q.ROLES)
    assert result["requires_no_build"] and not result["runtime_qualified"]


def running_row(a,role):
    image=next(row for row in a.receipt["images"] if row["role"]==role)
    cid=str(q.ROLES.index(role)+1)*64
    mounts={
        "skeleton":[{"Destination":"/app/data","Type":"volume","RW":True,"Name":PROJECT+"_skeleton_data"},
                    {"Destination":"/app/local-ai","Type":"bind","RW":False}],
        "backend":[{"Destination":"/app/data","Type":"volume","RW":True,"Name":PROJECT+"_backend_data"}],
        "frontend":[],
    }[role]
    ports=q._ports(a,8080)
    row={"id":cid,"name":"/"+q.NAMES[role],"image":image["image_id"],"running":True,
         "status":"running","labels":{q.PROJECT_LABEL:PROJECT,q.SERVICE_LABEL:role},
         "ports":{str(q.CONTAINER_PORTS[role])+"/tcp":[{"HostIp":"127.0.0.1","HostPort":str(ports[role])}]},
         "networks":{PROJECT+"_tutolage":{"NetworkID":NET}},"mounts":mounts}
    return image,row,ports


@pytest.mark.parametrize("role",q.ROLES)
def test_exact_running_container_image_and_mount_scope(monkeypatch,role):
    a=approved()
    image,row,ports=running_row(a,role)
    monkeypatch.setattr(q,"_ids",lambda *args:[row["id"]])
    monkeypatch.setattr(q,"_inspect",lambda *args:row)
    result=q._running_container(None,a,image,ports)
    assert result["image_id"]==image["image_id"] and result["container_id"]==row["id"]
    assert result["network_id"]==NET


@pytest.mark.parametrize("mutation",[
    lambda r:r.update(image="sha256:"+"0"*64),
    lambda r:r.update(running=False),lambda r:r.update(status="restarting"),
    lambda r:r["labels"].update({q.PROJECT_LABEL:"foreign"}),
    lambda r:r["ports"]["8001/tcp"][0].update(HostIp="0.0.0.0"),
    lambda r:r["mounts"].append({"Destination":"/app","Type":"bind","RW":False}),
    lambda r:r["mounts"][0].update(Name="foreign_data"),
    lambda r:r["mounts"][0].update(RW=False),
    lambda r:r["mounts"].pop(),
    lambda r:r["networks"].update(other={"NetworkID":NET}),
])
def test_container_identity_drift_denied(monkeypatch,mutation):
    a=approved()
    image,row,ports=running_row(a,"skeleton")
    mutation(row)
    monkeypatch.setattr(q,"_ids",lambda *args:[row["id"]])
    monkeypatch.setattr(q,"_inspect",lambda *args:row)
    with pytest.raises(q.ImageQualificationDenied):
        q._running_container(None,a,image,ports)


def test_two_rounds_do_not_promote_other_readiness_lanes(monkeypatch):
    a=approved()
    monkeypatch.setattr(q,"_assert_source",lambda *args:None)
    monkeypatch.setattr(q.time,"sleep",lambda *args:None)
    rows=[{"role":role,"container_id":str(i+1)*64} for i,role in enumerate(q.ROLES)]
    monkeypatch.setattr(q,"_observe",lambda *args:rows)
    result=q.observe_running(a,8080)
    assert result["running_image_ids_verified"] and result["passes"]==2
    assert all(result[key] is False for key in (
        "service_health_qualified","inference_qualified","device_qualified","release_qualified"))


def test_second_observation_drift_denies(monkeypatch):
    a=approved()
    monkeypatch.setattr(q,"_assert_source",lambda *args:None)
    monkeypatch.setattr(q.time,"sleep",lambda *args:None)
    rows=iter([[{"container_id":"1"*64}],[{"container_id":"2"*64}]])
    monkeypatch.setattr(q,"_observe",lambda *args:next(rows))
    with pytest.raises(q.ImageQualificationDenied):
        q.observe_running(a,8080)
