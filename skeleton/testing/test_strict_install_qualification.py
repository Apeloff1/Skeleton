"""Adversarial strict first-install acceptance using actual loopback transports."""
from __future__ import annotations

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from contextlib import contextmanager
import pytest

from skeleton.app import strict_install_qualification as q
from skeleton.app.assembly import load_manifest
from skeleton.app.bootstrap import public_bootstrap_payload


def fixtures(protected=True):
    bootstrap=public_bootstrap_payload()
    engine=q._component(bootstrap,"engine","/api/v1")
    writer={"ok":True,"required":protected,
            "code":"protected_writer_binding_observed" if protected else "legacy_writer_mode_unqualified",
            "known_local_writer_binding_observed":protected,
            "external_writer_coverage_verified":False,"guarded_local_ai_ready":False}
    backend={"status":"ready","canonical_application":q._component(bootstrap,"backend","/api"),
             "checks":{**{key:{"ok":True} for key in q._REQUIRED_CHECKS},
                       "canonical_writer_custody":writer}}
    aggregate={"ok":True,"scope":"public-runtime","application":bootstrap["application"],
               "contract":bootstrap["contract"],
               "services":[{"name":"backend","ok":True,"status":200},
                           {"name":"mongo","ok":True,"status":200},
                           {"name":"skeleton","ok":True,"status":200,"application":engine}],
               "product":{"available":True,"canonical_actions":10,"ready_actions":8,
                          "governed_unbound":2,"unsafe_actions":0,"policy_gaps":0,
                          "attestation_sha256":"a"*64}}
    return bootstrap,{
        "/setup":b"<!DOCTYPE html><html>setup</html>",
        "/product":b"<!DOCTYPE html><html>product</html>",
        "/api/app/bootstrap":bootstrap,
        "/api/health/ready":backend,
        "/api/v1/health/live":{"alive":True,"application":engine},
        "/api/app/ready":aggregate,
        "/api/app/status":deepcopy(aggregate),
        "/api/health/registry":{"critical_routes":{"ok":True,"report_available":True,"missing":[]}},
        "/api/ai/providers":{"engine":"skeleton-engine","providers":["local"],"active":"local",
                             "llm_available":True,"availability_observed":True},
    }


@contextmanager
def serve(responses):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            calls.append(self.path)
            value=responses[self.path]
            if type(value) is tuple:
                status,headers,body=value
            elif type(value) is bytes:
                status,headers,body=200,{"Content-Type":"text/html"},value
            else:
                status,headers,body=200,{"Content-Type":"application/json"},json.dumps(value).encode()
            self.send_response(status)
            for key,val in headers.items():
                self.send_header(key,val)
            self.end_headers()
            self.wfile.write(body)
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}",calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def run_worker(responses,bootstrap):
    with serve(responses) as (base,calls):
        result=q._worker({"bases":dict.fromkeys(("frontend","backend","skeleton"),base),
                          "bootstrap":bootstrap,"timeout":2,"selected_provider":"local"})
        return result,calls


def test_nine_live_lanes_and_scoped_acceptance():
    bootstrap,rows=fixtures()
    result,calls=run_worker(rows,bootstrap)
    assert len(calls)==len(q._LANES)==9
    assert len(set(calls))==9
    assert all(x["ok"] for x in q._validate_worker_result(result))
    scope=q._pass_scope(result)
    assert scope["services_observed"] and scope["protected_writer_observed"] and scope["provider_available_observed"]


def test_legacy_install_never_reports_protected_observation():
    bootstrap,rows=fixtures(False)
    result,_=run_worker(rows,bootstrap)
    scope=q._pass_scope(result)
    assert scope["services_observed"] and not scope["protected_writer_observed"]


@pytest.mark.parametrize("path,mutation",[
    ("/api/app/bootstrap",lambda v:v["application"].update(version="fake")),
    ("/api/app/bootstrap",lambda v:v.update(schema_version=True)),
    ("/api/health/ready",lambda v:v["checks"]["mongo"].update(ok=1)),
    ("/api/health/ready",lambda v:v["checks"]["canonical_writer_custody"].update(guarded_local_ai_ready=True)),
    ("/api/health/ready",lambda v:v["checks"].pop("canonical_writer_custody")),
    ("/api/health/ready",lambda v:v.update(status="not_ready")),
    ("/api/v1/health/live",lambda v:v.update(alive=1)),
    ("/api/v1/health/live",lambda v:v["application"].update(component="backend")),
    ("/api/app/ready",lambda v:v["services"].append(v["services"][0])),
    ("/api/app/ready",lambda v:v["services"][0].update(ok=1)),
    ("/api/app/ready",lambda v:v["product"].update(unsafe_actions=1)),
    ("/api/app/ready",lambda v:v["product"].update(policy_gaps=1)),
    ("/api/app/ready",lambda v:v["product"].update(attestation_sha256="0"*64)),
    ("/api/app/status",lambda v:v["product"].update(attestation_sha256="b"*64)),
    ("/api/health/registry",lambda v:v["critical_routes"].update(missing=["private-value"])),
])
def test_contradictory_or_wrong_identity_required_lanes_fail(path,mutation):
    bootstrap,rows=fixtures()
    mutation(rows[path])
    result,_=run_worker(rows,bootstrap)
    assert q._pass_scope(result)["services_observed"] is False
    assert "private-value" not in json.dumps(result)


@pytest.mark.parametrize("bad",[
    (302,{"Location":"http://127.0.0.1:1/other","Content-Type":"application/json"},b"{}"),
    (200,{"Content-Type":"application/json"},b'{"alive":true,"alive":false}'),
    (200,{"Content-Type":"application/json"},b'{"x":Infinity}'),
    (200,{"Content-Type":"application/json"},b'{"x":1e999}'),
    (200,{"Content-Type":"text/html"},b"<!DOCTYPE html>"),
    (200,{"Content-Type":"application/json","Content-Encoding":"gzip"},b"{}"),
    (200,{"Content-Type":"application/json","Content-Length":"99999999"},b"{}"),
])
def test_transport_and_json_hostile_replies_denied(bad):
    with serve({"/health":bad}) as (base,calls):
        code,payload=q._get(base,"/health",timeout=1)
        assert code!="observed" and payload is None and calls==["/health"]


@pytest.mark.parametrize("base",["http://foo.example:80","http://127.0.0.1:80/x",
    "http://user:pass@127.0.0.1:80","http://127.0.0.1:80?bad","https://127.0.0.1:80",
    "http://127.0.0.1","http://localhost:80/#bad","http://localhost:0","http://localhost:\n80"])
def test_nonlocal_or_ambiguous_origins_denied(base):
    with pytest.raises((q.QualificationDenied,ValueError)):
        q._base(base)


def test_provider_unavailable_is_independently_held():
    bootstrap,rows=fixtures()
    rows["/api/ai/providers"]["active"]="openai"
    result,_=run_worker(rows,bootstrap)
    scope=q._pass_scope(result)
    assert scope["services_observed"] and not scope["provider_available_observed"]


def patch_host(monkeypatch,root,rounds):
    manifest=load_manifest()
    monkeypatch.setattr(q,"assert_source_head",lambda r,h:None)
    monkeypatch.setattr(q,"runtime_source_fingerprint",lambda r:"e"*64)
    monkeypatch.setattr("skeleton.app.assembly._runtime_env",lambda r,e:{"AI_PROVIDER":"local"})
    monkeypatch.setattr(q,"runtime_manifest",lambda m,**kw:m)
    monkeypatch.setattr(q.time,"sleep",lambda s:None)
    it=iter(rounds)
    monkeypatch.setattr(q,"_bounded_worker",lambda *a:next(it))


def clean_rows():
    bootstrap,payload=fixtures()
    return run_worker(payload,bootstrap)[0]


def test_two_round_receipt_separates_actual_inference_and_release(monkeypatch,tmp_path):
    rows=clean_rows()
    patch_host(monkeypatch,tmp_path,[rows,deepcopy(rows)])
    result=q.qualify_live_install(tmp_path,source_head="a"*40,require_protected=True,require_ai=True)
    assert result["ok"] and result["source_observed"] and len(result["rounds"])==2
    assert not any(result[key] for key in ("inference_qualified","running_image_source_verified",
        "browser_execution_verified","durable_restore_verified","device_qualified","release_qualified"))
    assert q._digest(result["receipt_sha256"])


def test_source_replacement_clears_previously_passing_rounds(monkeypatch,tmp_path):
    rows=clean_rows()
    patch_host(monkeypatch,tmp_path,[rows,rows])
    fingerprints=iter(["e"*64,"e"*64,"e"*64,"f"*64])
    monkeypatch.setattr(q,"runtime_source_fingerprint",lambda root:next(fingerprints))
    result=q.qualify_live_install(tmp_path,source_head="a"*40)
    assert result["ok"] is False and result["rounds"]==[] and result["source_observed"] is False


def test_product_authority_change_between_rounds_denies(monkeypatch,tmp_path):
    rows=clean_rows()
    changed=deepcopy(rows)
    for row in changed:
        if row["name"] in ("aggregate_ready","aggregate_status"):
            row["facts"]["product_attestation_sha256"]="c"*64
    patch_host(monkeypatch,tmp_path,[rows,changed])
    assert q.qualify_live_install(tmp_path,source_head="a"*40)["ok"] is False


def test_worker_packet_cannot_reflect_remote_text():
    rows=clean_rows()
    rows[0]["facts"]={"credential":"not-for-output"}
    with pytest.raises(q.QualificationDenied):
        q._validate_worker_result(rows)


def test_isolated_worker_process_over_real_loopback():
    bootstrap,rows=fixtures()
    with serve(rows) as (base,calls):
        result=q._bounded_worker(Path(q.__file__).resolve().parents[2],
            {"bases":dict.fromkeys(("frontend","backend","skeleton"),base),
             "bootstrap":bootstrap,"timeout":2,"selected_provider":"local"},10)
    assert q._pass_scope(result)["services_observed"]
    assert len(calls)==9



@pytest.mark.parametrize("name,facts", [
    ("backend_health", {}),
    ("backend_health", {"writer_mode":"protected_unavailable"}),
    ("aggregate_ready", {}),
    ("aggregate_status", {"product_attestation_sha256":"a"*64,
                          "canonical_actions":0,"ready_actions":0,"governed_unbound":0}),
    ("aggregate_status", {"product_attestation_sha256":"a"*64,
                          "canonical_actions":10,"ready_actions":11,"governed_unbound":0}),
    ("aggregate_status", {"product_attestation_sha256":"a"*64,
                          "canonical_actions":10,"ready_actions":8,"governed_unbound":11}),
    ("critical_routes", {}),
    ("critical_routes", {"missing_count":1}),
    ("critical_routes", {"missing_count":False}),
    ("provider_readiness", {}),
    ("provider_readiness", {"provider_available":False}),
])
def test_positive_worker_lane_requires_consistent_mandatory_facts(name,facts):
    rows=clean_rows()
    next(row for row in rows if row["name"]==name)["facts"]=facts
    with pytest.raises(q.QualificationDenied):
        q._validate_worker_result(rows)


def test_worker_selected_provider_must_match_parent_configuration():
    rows=clean_rows()
    next(row for row in rows if row["name"]=="provider_readiness")["facts"]["selected_provider"]="openai"
    with pytest.raises(q.QualificationDenied):
        q._validate_worker_result(rows,selected="local")


@pytest.mark.parametrize("key,new_value",[
    ("canonical_actions",11),("ready_actions",7),("governed_unbound",3),
])
def test_same_attestation_cannot_hide_round_counter_drift(monkeypatch,tmp_path,key,new_value):
    rows=clean_rows()
    changed=deepcopy(rows)
    for row in changed:
        if row["name"] in ("aggregate_ready","aggregate_status"):
            row["facts"][key]=new_value
    patch_host(monkeypatch,tmp_path,[rows,changed])
    result=q.qualify_live_install(tmp_path,source_head="a"*40)
    assert result["ok"] is False
    assert result["service_observation_complete"] is False


def test_parent_rejects_fabricated_worker_packet_even_after_initial_success(monkeypatch,tmp_path):
    rows=clean_rows()
    changed=deepcopy(rows)
    next(row for row in changed if row["name"]=="critical_routes")["facts"]={}
    patch_host(monkeypatch,tmp_path,[rows,changed])
    result=q.qualify_live_install(tmp_path,source_head="a"*40)
    assert result["ok"] is False and not result["rounds"]


@pytest.mark.parametrize("base",[
    "http://localhost:80?", "http://localhost:80#", "http://local%68ost:80",
])
def test_strict_loopback_rejects_empty_delimiters_and_encoded_authority(base):
    with pytest.raises(q.QualificationDenied):
        q._base(base)


@pytest.mark.parametrize("path",["/../health","/api//health","/api/%2e","/api/x?","/api/x#",
                                  "/api/\\x","/"+"x"*512])
def test_strict_probe_rejects_noncanonical_path_before_transport(monkeypatch,path):
    def forbidden(*args,**kwargs):
        pytest.fail("inadmissible route reached HTTP transport")
    monkeypatch.setattr(q.http.client,"HTTPConnection",forbidden)
    with pytest.raises(q.QualificationDenied):
        q._get("http://localhost:80",path,timeout=1)


@pytest.mark.parametrize("body",[b"<!doctype html-not-real>",b"<!doctype html",b"<html>"])
def test_html_prefix_cannot_qualify_setup_document(body):
    with serve({"/setup":body}) as (base,_):
        assert q._get(base,"/setup",timeout=1,html=True)[0]!="observed"



@pytest.fixture
def pinned_checkout(tmp_path):
    import shutil
    import subprocess
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not installed")
    root = tmp_path / "checkout"
    root.mkdir()

    def run(*args):
        return subprocess.run([git,"-C",str(root),*args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    run("init")
    run("config","user.name","Install Fixture")
    run("config","user.email","fixture@example.invalid")
    (root/"skeleton"/"app").mkdir(parents=True)
    (root/"skeleton"/"__init__.py").write_text("# fixture\n")
    (root/"skeleton"/"app"/"owner.py").write_text("VERSION=1\n")
    (root/".gitignore").write_text(".env\n__pycache__/\nshadow.py\n")
    run("add",".")
    run("commit","-m","source fixture")
    return root,run,run("rev-parse","HEAD").decode().strip()


def test_strict_source_pin_accepts_clean_checkout_and_ignored_private_runtime(pinned_checkout):
    root,run,head=pinned_checkout
    (root/".env").write_text("PRIVATE=fixture")
    cache=root/"skeleton"/"app"/"__pycache__"
    cache.mkdir()
    (cache/"owner.cpython-311.pyc").write_bytes(b"cache fixture")
    q.assert_source_head(root,head)


@pytest.mark.parametrize("flag",["--assume-unchanged","--skip-worktree"])
def test_strict_source_pin_rejects_hidden_index_entries(pinned_checkout,flag):
    root,run,head=pinned_checkout
    run("update-index",flag,"skeleton/app/owner.py")
    (root/"skeleton"/"app"/"owner.py").write_text("VERSION=2\n")
    with pytest.raises(q.QualificationDenied):
        q.assert_source_head(root,head)


@pytest.mark.parametrize("name",["shadow.py","extra.py","extra.pyc","extra.pyd","extra.so","extra.pth"])
def test_strict_source_pin_rejects_unreviewed_worker_import_inputs(pinned_checkout,name):
    root,run,head=pinned_checkout
    (root/"skeleton"/"app"/name).write_bytes(b"fixture")
    with pytest.raises(q.QualificationDenied):
        q.assert_source_head(root,head)


def test_strict_source_pin_rejects_ancestor_checkout_discovery(pinned_checkout):
    root,run,head=pinned_checkout
    with pytest.raises(q.QualificationDenied):
        q.assert_source_head(root/"skeleton",head)


@pytest.mark.parametrize("raw",[b"H tracked",b"H path\0\0",b"H "+b"x"*32769+b"\0"])
def test_index_observation_rejects_incomplete_or_overlong_records(raw):
    with pytest.raises(q.QualificationDenied):
        q._index_records(raw)
