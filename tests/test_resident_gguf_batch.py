"""Private socket transport and native batch policy source regressions."""
import os
import socket
import threading
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference.resident_gguf_batch import (
    ResidentBatchPolicy, _PrivateConnection, _strict_object,
)


def test_resident_batch_policy_refuses_unbounded_or_cpu_profiles():
    for override in ({"gpu_layers":0}, {"slots":1}, {"slots":33},
                     {"microbatch_tokens":1024}, {"context_per_slot":131073},
                     {"flash_attention":"unknown"}):
        values = dict(slots=2, context_per_slot=1024, gpu_layers=1, max_memory_bytes=1024**3)
        values.update(override)
        with pytest.raises(ValueError):
            ResidentBatchPolicy(**values)


def test_duplicate_server_json_fields_denied():
    with pytest.raises(ValueError, match="duplicate"):
        _strict_object([("tokens", []), ("tokens", [1])])


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux peer credentials required")
def test_private_connection_validates_pid_before_transmitting(tmp_path):
    endpoint = tmp_path / "local.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    listener.listen(2)
    seen = []
    def handle():
        with listener:
            for _ in range(2):
                conn, _ = listener.accept()
                with conn:
                    seen.append(conn.recv(64))
    worker = threading.Thread(target=handle)
    worker.start()
    try:
        wrong = _PrivateConnection(endpoint, os.getpid()+1, timeout=1)
        with pytest.raises(PermissionError):
            wrong.connect()
        right = _PrivateConnection(endpoint, os.getpid(), timeout=1)
        right.connect()
        right.sock.sendall(b"local-only")
        right.close()
    finally:
        worker.join(timeout=2)
    assert seen == [b"", b"local-only"]

def test_native_spill_transfer_encrypts_and_authenticates_actual_bytes(tmp_path):
    from types import SimpleNamespace
    import time
    from cryptography.exceptions import InvalidTag
    from skeleton.ai.runtime.inference.resident_gguf_batch import ResidentGGUFBatch
    session = object.__new__(ResidentGGUFBatch)
    session._model = SimpleNamespace(model_digest="a"*64)
    session._deadline = time.monotonic()+30
    raw = tmp_path/"raw"
    data = b"native-private-cache"*100000
    raw.write_bytes(data)
    sealed = tmp_path/"sealed"
    key = b"k"*32
    session._spill_transfer(raw, sealed, key=key, slot=0, size=len(data), encrypt=True)
    assert data[:128] not in sealed.read_bytes()
    restored = tmp_path/"restored"
    session._spill_transfer(sealed, restored, key=key, slot=0, size=len(data), encrypt=False)
    assert restored.read_bytes() == data
    with pytest.raises(InvalidTag):
        session._spill_transfer(sealed, tmp_path/"wrong-slot", key=key, slot=1, size=len(data), encrypt=False)

@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux native transport")
def test_real_child_residency_and_concurrent_private_requests(tmp_path):
    import hashlib
    import struct
    import sys
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppModel
    from skeleton.ai.runtime.inference.resident_gguf_batch import ResidentGGUFBatch

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    executable = runtime_dir / "fixture-server"
    executable.write_text(f"#!{sys.executable}\n" + '''
import http.server, json, socketserver, sys, threading
endpoint = sys.argv[sys.argv.index("--host")+1]
key = open(sys.argv[sys.argv.index("--api-key-file")+1]).read().strip()
barrier = threading.Barrier(2)
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def send(self, value):
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        self.send({"status":"ok"})
    def do_POST(self):
        assert self.headers["Authorization"] == "Bearer " + key
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tokenize":
            self.send({"tokens":[ord(data["content"][0])]})
        else:
            barrier.wait(timeout=5)
            assert data["cache_prompt"] is False
            self.send({"content":chr(data["prompt"][0]),"tokens":data["prompt"],
                       "stop_type":"limit","truncated":False})
class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads=True
print("load_tensors: offloaded 1/2 layers to GPU",flush=True)
with Server(endpoint, Handler) as server:
    server.serve_forever()
''')
    executable.chmod(0o700)
    model_path = tmp_path / "model.gguf"
    def string(text):
        raw=text.encode()
        return struct.pack("<Q",len(raw))+raw
    fields={"general.architecture":"llama","llama.context_length":256,
            "llama.embedding_length":8,"llama.block_count":1,
            "llama.attention.head_count":2,"llama.attention.head_count_kv":2}
    data=bytearray(struct.pack("<4sIQQ",b"GGUF",3,1,len(fields)))
    for name,value in fields.items():
        data+=string(name)
        data+=(struct.pack("<I",8)+string(value) if isinstance(value,str)
               else struct.pack("<II",4,value))
    model_path.write_bytes(data+bytes(1024))
    model=LlamaCppModel(LlamaCppConfig(executable=str(executable),model_path=str(model_path),
        context_size=256,gpu_layers=1,rehash_artifacts_each_run=True))
    policy=ResidentBatchPolicy(2,128,1,1024**3,timeout_seconds=10,max_session_seconds=30)
    with ResidentGGUFBatch(model,executable,hashlib.sha256(executable.read_bytes()).hexdigest(),policy) as session:
        pid=session._proc.pid
        assert [r["text"] for r in session.generate(["apple","banana"],max_new_tokens=1)["results"]]==["a","b"]
        assert [r["text"] for r in session.generate(["cherry","date"],max_new_tokens=1)["results"]]==["c","d"]
        assert session._proc.pid==pid
    assert session._proc.poll() is not None
    # This fixture intentionally prints a synthetic offload log; not GPU qualification.


def test_native_slot_endpoint_allowlist():
    from types import SimpleNamespace
    from skeleton.ai.runtime.inference.llama_cpp import LlamaCppRuntimeError
    from skeleton.ai.runtime.inference.resident_gguf_batch import ResidentGGUFBatch
    session = object.__new__(ResidentGGUFBatch)
    session._spill_temp = object()
    session._policy = SimpleNamespace(slots=2)
    session._proc = None
    for action in ("save", "restore", "erase"):
        with pytest.raises(LlamaCppRuntimeError, match="child unavailable"):
            session._call(f"/slots/1?action={action}", {}, deadline=0)
    for endpoint in ("/slots/2?action=save", "/slots/1action=save", "/slots/1?action=delete", "/slots/0?action=save&extra=1"):
        with pytest.raises(ValueError, match="unapproved native endpoint"):
            session._call(endpoint, {}, deadline=0)
