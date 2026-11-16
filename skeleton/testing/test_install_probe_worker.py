"""Reviewable source test of the exact frozen worker protocol."""
from __future__ import annotations
import io
import json
import sys
from pathlib import Path

import pytest
from skeleton.app import install_probe_worker as worker


def packet(**changes):
    value={"base":"http://127.0.0.1:3001","token":None,"timeout":2,
           "endpoint":"/api/health/registry","schema":None,"max_response_bytes":65536}
    value.update(changes)
    return json.dumps(value).encode()


@pytest.mark.parametrize("changes", [
    {"endpoint":"/other"},{"schema":"wrong"},{"token":"fixture-token-with-length"},
    {"base":"http://example.invalid:80"},{"base":"http://localhost:80?"},
    {"base":"http://localhost"},{"base":"http://user:secret@localhost:80"},
    {"base":"https://localhost:80"},{"timeout":True},{"timeout":0},
    {"timeout":float("nan")},{"max_response_bytes":True},{"max_response_bytes":2**31},
    {"extra":"unreviewed"}, {"endpoint":"/api/game-studio-health","schema":"skeleton.game.studio_readiness.v1"},
])
def test_worker_refuses_unadmitted_input_before_dispatch(monkeypatch,changes):
    def forbidden(**kwargs):
        pytest.fail("invalid worker input reached the transport")
    monkeypatch.setattr("skeleton.app.studio_readiness._server_snapshot",forbidden)
    output=io.BytesIO()
    assert worker.main([worker.FLAG],input_stream=io.BytesIO(packet(**changes)),output_stream=output)==2
    assert output.getvalue()==b""


@pytest.mark.parametrize("raw",[b"{}", b'{"x":1,"x":2}', b"\xff", b"x"*(65536+1)])
def test_worker_rejects_malformed_or_unbounded_packet(raw):
    with pytest.raises((ValueError,UnicodeError)):
        worker.decode_request(raw)


def test_worker_valid_packet_invokes_only_canonical_transport(monkeypatch):
    seen=[]
    def snapshot(**kwargs):
        seen.append(kwargs)
        return {"observed":True,"report":{"status":"fixture"}}
    monkeypatch.setattr("skeleton.app.studio_readiness._server_snapshot",snapshot)
    output=io.BytesIO()
    assert worker.main([worker.FLAG],input_stream=io.BytesIO(packet()),output_stream=output)==0
    assert json.loads(output.getvalue())["observed"] is True
    assert seen==[json.loads(packet())]


def test_worker_rejects_extra_flags_without_reading_input():
    class Unreadable:
        def read(self,*args): pytest.fail("unexpected worker read")
    assert worker.main([worker.FLAG,"other"],input_stream=Unreadable(),output_stream=io.BytesIO())==2


def test_frozen_uses_installed_console_not_windowed_python_flags(tmp_path,monkeypatch):
    launcher=tmp_path/"Skeleton.exe"
    console=tmp_path/worker.CONSOLE
    console.write_bytes(b"fixture")
    monkeypatch.setattr(sys,"frozen",True,raising=False)
    monkeypatch.setattr(sys,"executable",str(launcher))
    assert worker.worker_command(tmp_path)==[str(console),worker.FLAG]
    console.unlink()
    with pytest.raises(OSError):
        worker.worker_command(tmp_path)


def test_frozen_worker_rejects_different_payload_root(tmp_path,monkeypatch):
    root=tmp_path/"install"
    root.mkdir()
    other=tmp_path/"other"
    other.mkdir()
    monkeypatch.setattr(sys,"frozen",True,raising=False)
    monkeypatch.setattr(sys,"executable",str(root/"Skeleton.exe"))
    with pytest.raises(ValueError,match="payload root"):
        worker.worker_command(other)


def test_source_worker_uses_isolated_interpreter(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,"frozen",False,raising=False)
    command=worker.worker_command(tmp_path)
    assert command[:5]==[sys.executable,"-I","-S","-B","-c"]
    assert command[-1]==worker.FLAG


def test_frozen_parent_resolves_worker_root_from_installed_executable_not_meipass(tmp_path,monkeypatch):
    from skeleton.app import first_install
    root=tmp_path/"installed"
    root.mkdir()
    monkeypatch.setattr(sys,"frozen",True,raising=False)
    monkeypatch.setattr(sys,"executable",str(root/"Skeleton.exe"))
    observed=[]
    def bounded(worker_root,base,token,timeout,**kwargs):
        observed.append((worker_root,base,token,kwargs["endpoint"]))
        return {"observed":True,"report":{"ok":True}}
    monkeypatch.setattr("skeleton.app.studio_readiness._bounded_server",bounded)
    assert first_install._bounded_json("http://127.0.0.1:32123/api/health/registry",timeout=1)=={"ok":True}
    assert observed==[(root,"http://127.0.0.1:32123",None,"/api/health/registry")]



def test_worker_huge_integer_timeout_is_redacted_denial():
    output=io.BytesIO()
    assert worker.main([worker.FLAG],input_stream=io.BytesIO(packet(timeout=2**10000)),output_stream=output)==2
    assert output.getvalue()==b""



@pytest.mark.parametrize("receipt",[
    {"observed":True,"report":{}},
    {"observed":True,"scope":"foreign","report":{}},
    {"observed":False,"code":"private-reflected-value"},
    {"observed":False,"code":"server_inventory_unavailable","http_status":True},
    {"observed":False,"code":"server_inventory_unavailable","extra":"secret"},
    {"observed":True,"scope":"Public backend readiness; no authentication or model execution.",
     "report":{"schema_version":"incorrect"}},
])
def test_parent_rejects_untrusted_worker_receipt_envelopes(receipt):
    from skeleton.app.studio_readiness import _validate_server_receipt
    assert _validate_server_receipt(receipt,token=None,schema="expected")=={
        "observed":False,"code":"server_inventory_protocol_invalid"}


def test_source_parent_supplies_ephemeral_cache_prefix(tmp_path,monkeypatch):
    import subprocess
    from skeleton.app import studio_readiness as studio
    paths=[]
    monkeypatch.setattr(studio.platform,"system",lambda:"Windows")
    monkeypatch.setattr(sys,"frozen",False,raising=False)
    payload={"observed":True,"scope":"Public backend readiness; no authentication or model execution.",
             "report":{"ok":True}}
    def run(command,**kwargs):
        index=command.index("-X")
        prefix=Path(command[index+1].split("=",1)[1])
        assert prefix.is_dir() and not list(prefix.iterdir())
        assert "-I" in command and "-S" in command and "-B" in command
        paths.append(prefix)
        kwargs["stdout"].write(json.dumps(payload).encode())
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(studio.subprocess,"run",run)
    assert studio._bounded_server(tmp_path,"http://localhost:12345",None,1,
            endpoint="/api/health/registry",schema=None)==payload
    assert len(paths)==1 and not paths[0].exists()
