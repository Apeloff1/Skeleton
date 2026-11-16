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
        first = session.generate(["apple","banana"],max_new_tokens=1)
        assert [r["text"] for r in first["results"]]==["a","b"]
        assert first["requested_tuning_sha256"] == policy.tuning.digest()
        assert first["generated_tokens"] == 2
        assert first["batch_wall_seconds"] >= first["tokenization_wall_seconds"] >= 0
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

def test_typed_native_tuning_is_default_neutral_and_charges_memory():
    from types import SimpleNamespace
    from skeleton.ai.runtime.inference.resident_gguf_batch import NativeResidentTuning
    default = NativeResidentTuning()
    assert default.arguments() == ()
    assert default.additional_memory_bytes == 0
    assert ResidentBatchPolicy(2, 128, 1, 1024**3).tuning == default
    tuning = NativeResidentTuning(numa="isolate", load_mode="mmap", lazy_mode="on",
        split_mode="tensor", tensor_split=(3, 1), cpu_moe_layers=8, moe_cache_mib=256,
        ngram_match=12, ngram_draft=24, extra_workspace_bytes=64*1024**2)
    tuning.validate_model(SimpleNamespace(architecture="qwen2moe", block_count=24),
                          context_per_slot=1024)
    assert tuning.arguments() == (
        "--numa", "isolate", "--load-mode", "mmap", "--lazy-mode", "on",
        "--split-mode", "tensor", "--tensor-split", "3,1", "--n-cpu-moe", "8",
        "--moe-cache-mib", "256", "--spec-type", "ngram-simple",
        "--spec-ngram-simple-size-n", "12", "--spec-ngram-simple-size-m", "24")
    assert tuning.additional_memory_bytes == 320*1024**2
    assert tuning.digest() != default.digest()


@pytest.mark.parametrize("kwargs", [
    {"prefill_threads": True}, {"prefill_threads": 0}, {"numa": "--host"},
    {"load_mode": "https://example.invalid/model"}, {"lazy_mode": "on"},
    {"split_mode": "tensor"}, {"tensor_split": (1, 2)},
    {"split_mode": "row", "tensor_split": (1, 0)},
    {"split_mode": "row", "tensor_split": [1, 2]},
    {"split_mode": "graph", "tensor_split": (1, 2)},
    {"cpu_moe_layers": 1, "cpu_ffn_layers": 1}, {"moe_cache_mib": 64},
    {"ngram_match": 12}, {"ngram_draft": 12}, {"ngram_match": 12, "ngram_draft": 16},
    {"extra_workspace_bytes": -1}, {"moe_cache_mib": True},
])
def test_typed_native_tuning_rejects_unbounded_options(kwargs):
    from skeleton.ai.runtime.inference.resident_gguf_batch import NativeResidentTuning
    with pytest.raises(ValueError):
        NativeResidentTuning(**kwargs)


def test_native_tuning_geometry_and_cpu_affinity(monkeypatch):
    from types import SimpleNamespace
    from skeleton.ai.runtime.inference.resident_gguf_batch import NativeResidentTuning
    model = SimpleNamespace(architecture="llama", block_count=8)
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 1}, raising=False)
    for tuning in (
        NativeResidentTuning(cpu_moe_layers=2),
        NativeResidentTuning(cpu_ffn_layers=9),
        NativeResidentTuning(ngram_match=64, ngram_draft=64, extra_workspace_bytes=64*1024**2),
        NativeResidentTuning(prefill_threads=3),
    ):
        with pytest.raises(ValueError):
            tuning.validate_model(model, context_per_slot=128)
    NativeResidentTuning(cpu_ffn_layers=8, prefill_threads=2).validate_model(
        model, context_per_slot=128)
    with pytest.raises(TypeError):
        ResidentBatchPolicy(2, 128, 1, 1024**3, tuning={"extra_args": ["--host"]})


def test_matched_tuning_benchmark_holds_output_drift_and_partial_rows():
    from scripts.benchmark_resident_gguf_tuning import summarize
    from copy import deepcopy
    case = {"case_sha256": "a"*64, "exact": True,
            "output_sha256": "b"*64, "token_ids_sha256": "c"*64}
    rows = [{"profile": name, "repeat": r, "offset": 0,
             "seconds": 2.0 if name == "baseline" else 1.0,
             "cases": [dict(case), dict(case)]}
            for name in ("baseline", "candidate") for r in range(2)]
    report = summarize(rows, ["baseline","candidate"], 2, [0], 2)
    assert report["summaries"]["candidate"]["parity_eligible"]
    assert report["summaries"]["candidate"]["median_paired_wall_speedup"] == 2
    bad = deepcopy(rows)
    bad[2]["cases"][0]["token_ids_sha256"] = "d"*64
    assert not summarize(bad, ["baseline","candidate"], 2, [0], 2)["summaries"]["candidate"]["parity_eligible"]
    unstable = deepcopy(rows)
    unstable[1]["cases"][0]["exact"] = False
    assert not summarize(unstable, ["baseline","candidate"], 2, [0], 2)["baseline_stable"]
    with pytest.raises(ValueError, match="incomplete"):
        summarize(rows[:-1], ["baseline","candidate"], 2, [0], 2)


def test_tuning_config_hash_and_duplicate_rejection(tmp_path):
    import hashlib
    from scripts.benchmark_resident_gguf_tuning import read_candidates
    path = tmp_path / "profiles.json"
    for data, succeeds in (
        (b'{"fast":{"prefill_threads":2}}', True),
        (b'{"fast":{"prefill_threads":2,"prefill_threads":4}}', False),
        (b'{"fast":{"extra_args":["--host"]}}', False),
        (b'{"fast":{}}', False),
        (b'{"fast":{"prefill_threads":2},"also":{"prefill_threads":2}}', False),
    ):
        path.write_bytes(data)
        pin = hashlib.sha256(data).hexdigest()
        if succeeds:
            assert read_candidates(path,pin)["fast"].prefill_threads == 2
            with pytest.raises(ValueError, match="identity"):
                read_candidates(path,"0"*64)
        else:
            with pytest.raises(ValueError):
                read_candidates(path,pin)


def test_prefix_affinity_matches_reordered_prompts_and_is_session_private():
    from skeleton.ai.runtime.inference.resident_gguf_batch import (
        _prefix_fingerprints, _match_prefix_slots,
    )
    key = b"a" * 32
    first = _prefix_fingerprints([1] * 64 + [3], key)
    second = _prefix_fingerprints([2] * 96, key)
    partial = _prefix_fingerprints([1] * 31, key)
    assert partial == ()
    assert first != _prefix_fingerprints([1] * 64, b"b" * 32)
    assert _match_prefix_slots([second, first], {0: first, 1: second}, (0, 1)) == ((1, 96), (0, 64))
    assert _match_prefix_slots([second, first], {0: first, 1: second}, (0, 2)) == ((2, 0), (0, 64))
    assert _match_prefix_slots([first, first], {0: first}, (0, 1)) == ((0, 64), (1, 0))
    with pytest.raises(ValueError):
        _match_prefix_slots([first, second], {0: first}, (0,))
    with pytest.raises(ValueError):
        ResidentBatchPolicy(2, 128, 1, 1024**3, prefix_affinity=True)
    assert ResidentBatchPolicy(2, 128, 1, 1024**3, slot_spill_bytes=1024,
                               prefix_affinity=True).prefix_affinity
