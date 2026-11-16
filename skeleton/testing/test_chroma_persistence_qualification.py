"""Source contracts for the isolated physical Chroma fixture."""
from __future__ import annotations

from copy import deepcopy
import pytest
from scripts import qualify_chroma_persistence as q


@pytest.mark.parametrize("patch",[
    {"Name":"foreign"},{"Driver":"nfs"},{"Labels":{}},{"Options":{"device":"/unexpected"}},
    {"Mountpoint":"relative"},
])
def test_wrong_volume_authority_denied(monkeypatch,patch):
    row={"Name":"fixture","Driver":"local","Labels":{q.LABEL:"token"},
         "Options":None,"Mountpoint":"/var/lib/docker/volumes/fixture/_data"}
    row.update(patch)
    monkeypatch.setattr(q,"_one_json",lambda *args:row)
    with pytest.raises(q.QualificationError):
        q._volume_identity("fixture","token")


def container():
    return {"Id":"a"*64,"Image":"sha256:"+"b"*64,"Labels":{q.LABEL:"token"},
        "Mounts":[{"Type":"volume","Name":"fixture","Destination":"/data","RW":True}],
        "State":{"Running":True},"Ports":{"8000/tcp":[{"HostIp":"127.0.0.1","HostPort":"12345"}]}}


@pytest.mark.parametrize("change",[
    lambda row:row["Labels"].clear(),
    lambda row:row["Mounts"][0].update(Destination="/chroma/chroma"),
    lambda row:row["Mounts"][0].update(Name="foreign"),
    lambda row:row["Mounts"][0].update(RW=False),
    lambda row:row["Mounts"].append({"Destination":"/data/sub"}),
    lambda row:row["Ports"]["8000/tcp"][0].update(HostIp="0.0.0.0"),
    lambda row:row.update(Image="sha256:"+"c"*64),
])
def test_wrong_mount_or_exposure_denied(monkeypatch,change):
    row=container()
    change(row)
    monkeypatch.setattr(q,"_one_json",lambda *args:row)
    with pytest.raises(q.QualificationError):
        q._container_identity("a"*64,"token","fixture","sha256:"+"b"*64)


def test_valid_fixture_binding(monkeypatch):
    monkeypatch.setattr(q,"_one_json",lambda *args:container())
    assert q._container_identity("a"*64,"token","fixture","sha256:"+"b"*64)==(True,12345)


@pytest.mark.parametrize("raw",[b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}',b"",b"{" ])
def test_fixture_json_strict(raw):
    with pytest.raises(q.QualificationError):
        q.decode(raw)


def test_cleanup_never_deletes_wrong_ownership(monkeypatch):
    calls=[]
    def docker(*args,**kwargs):
        calls.append(args)
        return 0,b"a"*64
    monkeypatch.setattr(q,"docker",docker)
    row=container()
    row["Labels"][q.LABEL]="different"
    monkeypatch.setattr(q,"_one_json",lambda *args:row)
    with pytest.raises(q.QualificationError):
        q._cleanup_container("fixture","token","fixture","sha256:"+"b"*64)
    assert not any(args[:2] in (("container","rm"),("container","stop")) for args in calls)


def test_persisted_vectors_are_checked_not_just_ids(monkeypatch):
    expected={"a":{"document":"a","metadata":{"revision":1},"embedding":[1.,0.,0.]}}
    good={"ids":["a"],"documents":["a"],"metadatas":[{"revision":1}],"embeddings":[[1.,0.,0.]]}
    observed=deepcopy(good)
    def request(port,method,path,payload=None):
        return 1 if path.endswith("/count") else observed
    monkeypatch.setattr(q,"request",request)
    cid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert len(q._assert_records(12345,cid,expected))==64
    observed["embeddings"][0][0]=0.
    with pytest.raises(q.QualificationError):
        q._assert_records(12345,cid,expected)


def test_path_never_accepts_arbitrary_collection():
    with pytest.raises(q.QualificationError):
        q._path("../../bad","get")
