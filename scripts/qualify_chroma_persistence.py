#!/usr/bin/env python3
"""Qualify the pinned Chroma /data persistence layout on a disposable volume.

No external daemon, supplied URI, application project, existing volume,
credential or real user data is accepted. Creates only randomly named and
label-bound local fixture resources. Never changes the legacy full profile.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "chromadb/chroma:latest@sha256:1e0b73a187a28757c572acba508c46f48c9e8b0acaf5c20e6d95cdedce1acdf6"
SCHEMA = "skeleton.chroma.isolated_persistence_qualification.v1"
LABEL = "org.skeleton.chroma-qualification"
_ID = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)
_IMAGE_ID = re.compile(r"sha256:[a-f0-9]{64}\Z", re.ASCII)
_UUID = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\Z", re.ASCII)
_MAX_JSON = 512 * 1024
_DOCKER = ["docker","--host","unix:///var/run/docker.sock"]


class QualificationError(RuntimeError):
    pass


def require(value, detail):
    if value is not True:
        raise QualificationError(detail)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _pairs(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,"duplicate fixture JSON field")
        result[key]=value
    return result


def _constant(_):
    raise QualificationError("nonfinite fixture JSON")


def _float(value):
    value=float(value)
    require(math.isfinite(value),"nonfinite fixture number")
    return value


def decode(raw):
    require(type(raw) is bytes and 0<len(raw)<=_MAX_JSON,"invalid fixture response size")
    try:
        return json.loads(raw.decode("utf-8","strict"),object_pairs_hook=_pairs,
                          parse_constant=_constant,parse_float=_float)
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        raise QualificationError("fixture JSON unavailable") from None


def docker(*args,timeout=30,required=True):
    env={"PATH":os.defpath,"HOME":"/tmp","LANG":"C.UTF-8","LC_ALL":"C.UTF-8"}
    try:
        with tempfile.TemporaryFile() as output:
            process=subprocess.run([*_DOCKER,*args],env=env,stdout=output,
                stderr=subprocess.DEVNULL,timeout=timeout,check=False)
            output.seek(0)
            raw=output.read(_MAX_JSON+1)
        require(len(raw)<=_MAX_JSON,"Docker fixture response exceeds bound")
        if required:
            require(process.returncode==0,"Docker fixture operation unavailable")
        return process.returncode,raw
    except (OSError,subprocess.SubprocessError):
        raise QualificationError("Docker fixture operation timed out or unavailable") from None


def _one_json(*args):
    _,raw=docker(*args)
    return decode(raw)


def source_head(expected):
    require(type(expected) is str and re.fullmatch(r"[0-9a-f]{40}",expected) is not None,
            "exact source head required")
    try:
        result=subprocess.run(["git","-C",str(ROOT),"rev-parse","HEAD"],stdout=subprocess.PIPE,
                   stderr=subprocess.DEVNULL,check=True,timeout=10)
        require(result.stdout.strip()==expected.encode("ascii"),"fixture source head changed")
    except (OSError,subprocess.SubprocessError):
        raise QualificationError("fixture source identity unavailable") from None


def _volume_identity(name,token):
    row=_one_json("volume","inspect","--format","{{json .}}",name)
    require(type(row) is dict and row.get("Name")==name and row.get("Driver")=="local"
            and type(row.get("Labels")) is dict and row["Labels"].get(LABEL)==token
            and row.get("Options") in (None,{})
            and type(row.get("Mountpoint")) is str and row["Mountpoint"].startswith("/"),
            "fixture volume identity not owned")
    return digest({"name":name,"mountpoint":row["Mountpoint"],
                   "driver":row["Driver"],"label":token,"created":row.get("CreatedAt")})


def _container_identity(cid,token,volume,image_id):
    require(type(cid) is str and _ID.fullmatch(cid) is not None,"fixture container ID invalid")
    # Query exact ID and only metadata required to prove cleanup/volume
    # ownership. Never inspect arbitrary app containers or expose their env.
    row=_one_json("container","inspect","--format",
                  '{"Id":{{json .Id}},"Image":{{json .Image}},"Labels":{{json .Config.Labels}},"Mounts":{{json .Mounts}},"State":{{json .State}},"Ports":{{json .NetworkSettings.Ports}}}',
                  cid)
    require(type(row) is dict and row.get("Id")==cid and row.get("Image")==image_id
            and type(row.get("Labels")) is dict and row["Labels"].get(LABEL)==token,
            "fixture container identity not owned")
    mounts=row.get("Mounts")
    require(type(mounts) is list and all(type(m) is dict for m in mounts),"fixture mount inventory invalid")
    data=[m for m in mounts if m.get("Destination")=="/data"]
    require(len(data)==1 and data[0].get("Type")=="volume" and data[0].get("Name")==volume
            and data[0].get("RW") is True and not any(
                type(m.get("Destination")) is str and
                (m["Destination"].startswith("/data/") or m["Destination"]=="/chroma/chroma")
                for m in mounts),"fixture persistence is not mounted exactly at /data")
    state=row.get("State")
    require(type(state) is dict and type(state.get("Running")) is bool,"fixture state unavailable")
    if not state["Running"]:
        return False,None
    ports=row.get("Ports")
    require(type(ports) is dict and type(ports.get("8000/tcp")) is list
            and len(ports["8000/tcp"])==1,"fixture port exposure invalid")
    published=ports["8000/tcp"][0]
    require(type(published) is dict and published.get("HostIp")=="127.0.0.1"
            and type(published.get("HostPort")) is str
            and re.fullmatch(r"[0-9]{1,5}",published["HostPort"]) is not None,
            "fixture port not loopback-only")
    port=int(published["HostPort"])
    require(1<=port<=65535,"fixture port invalid")
    return True,port


def _create_container(name,token,volume,image_id):
    _,raw=docker("container","create","--name",name,"--label",LABEL+"="+token,
        "--publish","127.0.0.1::8000","--mount",f"type=volume,source={volume},target=/data",
        "--security-opt","no-new-privileges:true","--memory","2g","--cpus","2",
        "--env","ANONYMIZED_TELEMETRY=FALSE",image_id,timeout=60)
    cid=raw.decode("ascii").strip()
    require(_ID.fullmatch(cid) is not None,"fixture container creation identity invalid")
    require(_container_identity(cid,token,volume,image_id)==(False,None),"fixture unexpectedly running")
    return cid


def _start(cid,token,volume,image_id):
    require(_container_identity(cid,token,volume,image_id)==(False,None),
            "fixture already running")
    docker("container","start",cid,timeout=60)
    running,port=_container_identity(cid,token,volume,image_id)
    require(running and port is not None,"fixture failed to start")
    return port


def _stop(cid,token,volume,image_id):
    running,_=_container_identity(cid,token,volume,image_id)
    if running:
        docker("container","stop","--time","30",cid,timeout=45)
    require(_container_identity(cid,token,volume,image_id)==(False,None),"fixture did not stop")


def _cleanup_container(name,token,volume,image_id):
    if name is None:
        return
    # Resolve only the unique generated name, then verify exact label and
    # image/mount custody before ever deleting that owned fixture.
    code,raw=docker("container","inspect","--format","{{.Id}}",name,required=False)
    if code:
        # A failed inspect is not proof of absence.
        _,raw=docker("container","ls","-a","--filter","name=^/"+name+"$","--format","{{.ID}}")
        require(not raw.strip(),"fixture cleanup identity uncertain")
        return
    cid=raw.decode("ascii").strip()
    _stop(cid,token,volume,image_id)
    docker("container","rm",cid)
    _,raw=docker("container","ls","-a","--filter","name=^/"+name+"$","--format","{{.ID}}")
    require(not raw.strip(),"fixture container cleanup failed")


def _cleanup_volume(volume,token):
    _,raw=docker("volume","ls","--filter","name=^"+volume+"$","--format","{{.Name}}")
    if not raw.strip():
        return
    require(raw.decode("ascii").strip()==volume,"fixture volume lookup ambiguous")
    _volume_identity(volume,token)
    # No --force: refuse a still-referenced volume.
    docker("volume","rm",volume)
    _,raw=docker("volume","ls","--filter","name=^"+volume+"$","--format","{{.Name}}")
    require(not raw.strip(),"fixture volume cleanup failed")


def request(port,method,path,payload=None):
    require(type(port) is int and 1<=port<=65535 and method in ("GET","POST","DELETE")
            and path.startswith("/api/v2/") and not any(ch in path for ch in "\r\n?#"),
            "fixture HTTP target invalid")
    conn=http.client.HTTPConnection("127.0.0.1",port=port,timeout=5)
    headers={"Accept":"application/json","Accept-Encoding":"identity","Connection":"close"}
    body=None
    if payload is not None:
        body=canonical(payload)
        require(len(body)<=_MAX_JSON,"fixture request exceeds bound")
        headers["Content-Type"]="application/json"
    try:
        conn.request(method,path,body=body,headers=headers)
        response=conn.getresponse()
        require(response.status in (200,201,204),"fixture API status denied")
        require(response.headers.get("Content-Encoding","identity").lower()=="identity",
                "fixture response encoding unsupported")
        raw=response.read(_MAX_JSON+1)
        require(len(raw)<=_MAX_JSON,"fixture API response exceeds bound")
        return None if not raw else decode(raw)
    except (OSError,http.client.HTTPException,TimeoutError):
        raise QualificationError("fixture API unavailable") from None
    finally:
        conn.close()


def _await_ready(port):
    deadline=time.monotonic()+75
    while time.monotonic()<deadline:
        try:
            heartbeat=request(port,"GET","/api/v2/heartbeat")
            version=request(port,"GET","/api/v2/version")
            require(type(heartbeat) is dict and type(version) is str
                    and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+.][a-zA-Z0-9.-]+)?",version) is not None,
                    "fixture heartbeat or version invalid")
            return version
        except QualificationError:
            time.sleep(1)
    raise QualificationError("fixture startup deadline exceeded")


def _collection_path():
    return "/api/v2/tenants/default_tenant/databases/default_database/collections"


def _create_collection(port,name):
    row=request(port,"POST",_collection_path(),{"name":name,"get_or_create":False,
        "metadata":{"qualification":"isolated-fixture"}})
    require(type(row) is dict and row.get("name")==name and type(row.get("id")) is str
            and _UUID.fullmatch(row["id"]) is not None,"fixture collection identity invalid")
    return row["id"]


def _collection_id(port,name):
    row=request(port,"GET",_collection_path()+"/"+quote(name,safe=""))
    require(type(row) is dict and row.get("name")==name and type(row.get("id")) is str
            and _UUID.fullmatch(row["id"]) is not None,"fixture collection missing")
    return row["id"]


def _path(cid,action):
    require(type(cid) is str and _UUID.fullmatch(cid) is not None
            and action in ("add","get","query","count","upsert","delete"),"fixture collection path invalid")
    return _collection_path()+"/"+cid+"/"+action


def _assert_records(port,cid,expected):
    count=request(port,"GET",_path(cid,"count"))
    require(type(count) is int and count==len(expected),"fixture record count mismatch")
    data=request(port,"POST",_path(cid,"get"),{"ids":sorted(expected),"include":["documents","metadatas","embeddings"]})
    require(type(data) is dict and type(data.get("ids")) is list
            and len(data["ids"])==len(expected) and set(data["ids"])==set(expected)
            and all(type(data.get(k)) is list and len(data[k])==len(expected)
                    for k in ("documents","metadatas","embeddings")),"fixture record inventory mismatch")
    normalized={}
    for index,key in enumerate(data["ids"]):
        document,metadata,vector=(data[k][index] for k in ("documents","metadatas","embeddings"))
        require(type(vector) is list and len(vector)==3 and all(type(x) in (int,float)
                and math.isfinite(x) for x in vector),"fixture embedding invalid")
        observed={"document":document,"metadata":metadata,"embedding":vector}
        require(observed==expected[key],"fixture persisted record diverged")
        normalized[key]=observed
    return digest(normalized)


def _assert_query(port,cid,expected_id):
    result=request(port,"POST",_path(cid,"query"),{"query_embeddings":[[1.,0.,0.]],
                "n_results":1,"include":["distances","documents","metadatas"]})
    require(type(result) is dict and result.get("ids")==[[expected_id]]
            and type(result.get("distances")) is list and len(result["distances"])==1
            and type(result["distances"][0]) is list and len(result["distances"][0])==1
            and type(result["distances"][0][0]) in (int,float)
            and abs(result["distances"][0][0])<=1e-5,"fixture vector index query diverged")


def _payload(rows):
    keys=sorted(rows)
    return {"ids":keys,"documents":[rows[k]["document"] for k in keys],
            "metadatas":[rows[k]["metadata"] for k in keys],
            "embeddings":[rows[k]["embedding"] for k in keys]}


def run(head):
    source_head(head)
    token=uuid4().hex
    volume="skeleton-chroma-qualification-"+token
    names=["skeleton-chroma-"+token+"-a","skeleton-chroma-"+token+"-b"]
    _,raw=docker("image","pull",IMAGE,timeout=180)
    _,raw=docker("image","inspect","--format","{{.Id}}",IMAGE)
    image_id=raw.decode("ascii").strip()
    require(_IMAGE_ID.fullmatch(image_id) is not None,"pinned fixture image identity unavailable")
    checks={}
    persistence_hash=None
    try:
        _,raw=docker("volume","create","--driver","local","--label",LABEL+"="+token,volume)
        require(raw.decode("ascii").strip()==volume,"fixture volume creation mismatch")
        volume_id=_volume_identity(volume,token)
        first=_create_container(names[0],token,volume,image_id)
        port=_start(first,token,volume,image_id)
        version=_await_ready(port)
        collection="skeleton-fixture-"+token
        cid=_create_collection(port,collection)
        expected={
            "a":{"document":"isolated-fixture-a","metadata":{"revision":1},"embedding":[1.,0.,0.]},
            "b":{"document":"isolated-fixture-b","metadata":{"revision":1},"embedding":[0.,1.,0.]},
            "c":{"document":"isolated-fixture-c","metadata":{"revision":1},"embedding":[0.,0.,1.]},
        }
        request(port,"POST",_path(cid,"add"),_payload(expected))
        first_hash=_assert_records(port,cid,expected)
        _assert_query(port,cid,"a")
        checks["real_vector_crud_and_index"]=True

        _stop(first,token,volume,image_id)
        port=_start(first,token,volume,image_id)
        require(_await_ready(port)==version and _collection_id(port,collection)==cid,
                "fixture restart collection identity changed")
        require(_assert_records(port,cid,expected)==first_hash,"fixture restart content changed")
        _assert_query(port,cid,"a")
        checks["same_container_restart_persistence"]=True

        # Mutate after restart to qualify durable update and deletion, not
        # merely a read-only stale copy.
        expected["b"]={"document":"isolated-fixture-b-updated","metadata":{"revision":2},
                       "embedding":[0.,-1.,0.]}
        request(port,"POST",_path(cid,"upsert"),_payload({"b":expected["b"]}))
        request(port,"POST",_path(cid,"delete"),{"ids":["c"]})
        del expected["c"]
        persistence_hash=_assert_records(port,cid,expected)
        _assert_query(port,cid,"a")
        checks["durable_update_delete"]=True

        _cleanup_container(names[0],token,volume,image_id)
        require(_volume_identity(volume,token)==volume_id,"fixture volume identity changed")
        second=_create_container(names[1],token,volume,image_id)
        require(second!=first,"fixture container recreation did not occur")
        port=_start(second,token,volume,image_id)
        require(_await_ready(port)==version and _collection_id(port,collection)==cid,
                "fixture recreation collection identity changed")
        require(_assert_records(port,cid,expected)==persistence_hash,"fixture recreation data changed")
        _assert_query(port,cid,"a")
        checks["new_container_same_volume_data_and_vector_index"]=True
        checks["verified_data_mount_and_volume_identity"]=_volume_identity(volume,token)==volume_id
        require(all(checks.values()),"fixture qualification incomplete")
    finally:
        # All cleanup paths verify generated identities before touching Docker.
        # No legacy/full-profile resources or unrelated images are removed.
        for name in names:
            _cleanup_container(name,token,volume,image_id)
        _cleanup_volume(volume,token)
    source_head(head)
    receipt={"schema":SCHEMA,"source_head":head,"image":IMAGE,"image_id":image_id,
             "version":version,"scope":"disposable_named_volume_only","checks":checks,
             "fixture_cleanup_verified":True,"synthetic_vector_state_sha256":persistence_hash,
             "legacy_migration_qualified":False,"production_full_profile_qualified":False,
             "release_qualified":False}
    receipt["receipt_sha256"]=digest(receipt)
    return receipt


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-head",required=True)
    parser.add_argument("--isolated-ci-fixture",action="store_true",required=True)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(run(args.source_head),sort_keys=True))
        return 0
    except Exception:
        print("Isolated Chroma persistence qualification denied; no passing receipt.",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
