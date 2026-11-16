"""Operator-scoped native llama.cpp continuous batching over a private Unix socket.

This is a local qualification/serving primitive under the existing inference
owner, not a product provider or a remote HTTP transport. The trusted native
binary, model, and adjacent libraries must be pinned; there is no downloader.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import tempfile
import threading
import time
from typing import Sequence

from .llama_cpp import (
    LlamaCppModel, LlamaCppRuntimeError, _identity, _runtime_library_identities,
    _runtime_library_names, _stat_matches, _sha256_file,
)
from .lease_custody import gguf_child_pass_fds

_HEX = re.compile(r"^[0-9a-f]{64}$")
_OFFLOAD = re.compile(rb"offloaded\s+(\d+)/(\d+)\s+layers to GPU")
_MAX_LOG_BYTES = 4 * 1024 * 1024
_MAX_REPLY_BYTES = 8 * 1024 * 1024


class _PrivateConnection(http.client.HTTPConnection):
    """HTTP framing exclusively over AF_UNIX; authenticate the owned child PID."""

    def __init__(self, path: Path, pid: int, *, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._path, self._pid = path, pid

    def connect(self):
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            peer.settimeout(self.timeout)
            peer.connect(os.fspath(self._path))
            raw = peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            pid, uid, _ = struct.unpack("3i", raw)
            if pid != self._pid or uid != os.geteuid():
                raise PermissionError("native server peer identity mismatch")
            self.sock = peer
        except BaseException:
            peer.close()
            raise


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate native JSON field")
        result[key] = value
    return result


def _bad_constant(_):
    raise ValueError("non-finite native JSON value")


@dataclass(frozen=True, slots=True)
class ResidentBatchPolicy:
    slots: int
    context_per_slot: int
    gpu_layers: int
    max_memory_bytes: int
    flash_attention: str = "auto"
    batch_tokens: int = 512
    microbatch_tokens: int = 128
    timeout_seconds: int = 120
    max_session_seconds: int = 3600
    max_batches: int = 128

    def __post_init__(self):
        bounds = (
            (self.slots, 2, 32), (self.context_per_slot, 128, 131072),
            (self.gpu_layers, 1, 4096), (self.max_memory_bytes, 1, 1024**4),
            (self.batch_tokens, 32, 8192), (self.microbatch_tokens, 16, 8192),
            (self.timeout_seconds, 1, 1800), (self.max_session_seconds, 1, 14400),
            (self.max_batches, 1, 1024),
        )
        if any(type(v) is not int or not lo <= v <= hi for v, lo, hi in bounds):
            raise ValueError("resident batch policy outside bounds")
        if self.slots * self.context_per_slot > 1_048_576:
            raise ValueError("aggregate native context exceeds ceiling")
        if self.microbatch_tokens > self.batch_tokens or self.flash_attention not in {"auto", "on", "off"}:
            raise ValueError("invalid native kernel/batch policy")


class ResidentGGUFBatch:
    """One explicitly owned native process, multiple bounded local batch calls."""

    def __init__(self, model: LlamaCppModel, server: Path, server_sha256: str,
                 policy: ResidentBatchPolicy, *, runtime_libraries=()):
        if not isinstance(model, LlamaCppModel) or not isinstance(policy, ResidentBatchPolicy):
            raise TypeError("admitted native model and resident policy required")
        if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
            raise OSError("Linux peer-authenticated Unix socket required")
        if not isinstance(server_sha256, str) or not _HEX.fullmatch(server_sha256):
            raise ValueError("server executable requires exact digest")
        self._model, self._policy = model, policy
        self._server = _identity(str(server), executable=True, reject_symlink=True)
        if self._server.sha256 != server_sha256:
            raise ValueError("native server digest mismatch")
        self._pins = tuple(runtime_libraries)
        self._libraries = _runtime_library_identities(Path(self._server.path).parent, self._pins) if self._pins else ()
        if not self._pins and _runtime_library_names(Path(self._server.path).parent):
            raise ValueError("adjacent server libraries require exact pins")
        if model.config.extra_args:
            raise ValueError("resident native batching requires raw pinned deployment")
        if model.config.gpu_layers is None or not 1 <= policy.gpu_layers <= model.config.gpu_layers:
            raise ValueError("resident GPU request exceeds explicit model profile")
        if policy.context_per_slot > model.generation_limits()["context_window"]:
            raise ValueError("resident per-slot context exceeds model profile")
        kv = model.serving_metadata.kv_bytes_per_token_upper_bound
        if kv is None:
            raise ValueError("resident batch requires known conservative KV geometry")
        self._estimate = model.total_model_bytes + model.config.runtime_scratch_bytes + (
            policy.slots * policy.context_per_slot * kv)
        if self._estimate > policy.max_memory_bytes:
            raise MemoryError("aggregate model/KV/scratch estimate exceeds operator budget")
        self._proc = None
        self._temp = None
        self._reader = None
        self._socket = None
        self._key = None
        self._ready = threading.Event()
        self._overflow = threading.Event()
        self._offloaded = None
        self._logs = bytearray()
        self._lock = threading.RLock()
        self._deadline = 0.0
        self._batches = 0
        self._closed = False

    def _assert_source(self):
        self._model.assert_identity()
        if not _stat_matches(self._server) or _sha256_file(Path(self._server.path)) != self._server.sha256:
            raise LlamaCppRuntimeError("resident executable changed")
        if self._pins:
            if _runtime_library_identities(Path(self._server.path).parent, self._pins) != self._libraries:
                raise LlamaCppRuntimeError("resident library inventory changed")
        elif _runtime_library_names(Path(self._server.path).parent):
            raise LlamaCppRuntimeError("unbound native runtime libraries appeared")

    def _drain_logs(self):
        try:
            with self._proc.stdout as stream:
                while True:
                    chunk = stream.read1(65536)
                    if not chunk:
                        return
                    if self._ready.is_set():
                        continue
                    if len(self._logs) + len(chunk) > _MAX_LOG_BYTES:
                        self._overflow.set()
                        continue
                    self._logs.extend(chunk)
        except OSError:
            self._overflow.set()

    def _call(self, endpoint, payload=None, *, deadline):
        if endpoint not in {"/health", "/tokenize", "/completion"}:
            raise ValueError("unapproved native endpoint")
        if self._proc is None or self._proc.poll() is not None or self._socket is None:
            raise LlamaCppRuntimeError("resident native child unavailable")
        remaining = min(deadline, self._deadline) - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("resident native deadline")
        connection = _PrivateConnection(self._socket, self._proc.pid, timeout=remaining)
        headers = {"Authorization": "Bearer " + self._key, "Content-Type": "application/json",
                   "Connection": "close"}
        try:
            body = None if payload is None else json.dumps(payload, separators=(",", ":"), allow_nan=False)
            connection.request("GET" if body is None else "POST", endpoint, body=body, headers=headers)
            response = connection.getresponse()
            if endpoint == "/health" and response.status == 503:
                return None
            if response.status != 200:
                raise LlamaCppRuntimeError("native server rejected bounded request")
            raw = bytearray()
            while True:
                remaining = min(deadline, self._deadline) - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("resident response deadline")
                # HTTPResponse can detach the connection socket on close; the
                # original socket timeout still provides a bounded read.
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read(min(65536, _MAX_REPLY_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > _MAX_REPLY_BYTES:
                    raise LlamaCppRuntimeError("native response exceeded byte ceiling")
            return json.loads(raw, object_pairs_hook=_strict_object, parse_constant=_bad_constant)
        finally:
            connection.close()

    def __enter__(self):
        with self._lock:
            if self._closed or self._proc is not None:
                raise RuntimeError("resident session is single-use")
            self._assert_source()
            self._temp = tempfile.TemporaryDirectory(prefix="skgguf-", dir="/tmp")
            root = Path(self._temp.name)
            self._socket = root / "engine.sock"
            self._key = secrets.token_hex(32)
            keyfile = root / "session.key"
            fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(self._key + "\n")
            p = self._policy
            args = [self._server.path, "-m", self._model.model_artifact.path,
                    "--host", str(self._socket), "--api-key-file", str(keyfile),
                    "--parallel", str(p.slots), "--cont-batching",
                    "-c", str(p.slots * p.context_per_slot), "-ngl", str(p.gpu_layers),
                    "-b", str(p.batch_tokens), "-ub", str(p.microbatch_tokens),
                    "--flash-attn", p.flash_attention, "--fit", "off",
                    "--no-context-shift", "--no-webui", "--no-slots", "--no-agent",
                    "--no-cache-prompt", "--cache-ram", "0", "--no-cache-idle-slots",
                    "--ctx-checkpoints", "0", "--no-kv-unified", "--timeout", str(p.timeout_seconds)]
            if self._model.config.threads is not None:
                args += ["-t", str(self._model.config.threads)]
            for field, flag in (("kv_cache_type_k", "--cache-type-k"), ("kv_cache_type_v", "--cache-type-v")):
                value = getattr(self._model.config, field)
                if value is not None:
                    args += [flag, value]
            if self._model.config.kv_cache_location == "host":
                args += ["--no-kv-offload"]
            self._deadline = time.monotonic() + p.max_session_seconds
            try:
                self._proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=root,
                    env={"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root),
                         "LANG": "C", "LC_ALL": "C"},
                    start_new_session=True, close_fds=True, pass_fds=gguf_child_pass_fds())
                self._reader = threading.Thread(target=self._drain_logs, daemon=True)
                self._reader.start()
                startup_deadline = min(self._deadline, time.monotonic() + p.timeout_seconds)
                while time.monotonic() < startup_deadline:
                    if self._proc.poll() is not None or self._overflow.is_set():
                        raise LlamaCppRuntimeError("native resident startup failed")
                    try:
                        response = self._call("/health", deadline=min(startup_deadline, time.monotonic()+1))
                    except (FileNotFoundError, ConnectionRefusedError, TimeoutError):
                        response = None
                    if isinstance(response, dict) and response.get("status") == "ok":
                        matches = _OFFLOAD.findall(bytes(self._logs))
                        if matches:
                            actual, total = map(int, matches[-1])
                            if 0 < actual <= total and actual == min(p.gpu_layers, total):
                                self._offloaded = (actual, total)
                                self._ready.set()
                                self._logs.clear()
                                self._assert_source()
                                return self
                    time.sleep(0.05)
                raise LlamaCppRuntimeError("native startup requires GPU offload evidence")
            except BaseException:
                self.close()
                raise

    def _tokenize(self, prompt, deadline):
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 1024**2:
            raise ValueError("bounded raw text prompt required")
        result = self._call("/tokenize", {"content": prompt, "add_special": True,
                                          "parse_special": False}, deadline=deadline)
        tokens = result.get("tokens") if isinstance(result, dict) else None
        if not isinstance(tokens, list) or not tokens or any(type(t) is not int or not 0 <= t <= 2**31-1 for t in tokens):
            raise LlamaCppRuntimeError("native tokenizer response rejected")
        return tokens

    def generate(self, prompts: Sequence[str], *, max_new_tokens: int, seed: int = 0):
        """Submit independent requests concurrently to the same native scheduler."""
        with self._lock:
            if not self._ready.is_set() or self._closed:
                raise RuntimeError("resident batch requires entered session")
            p = self._policy
            if self._batches >= p.max_batches:
                raise RuntimeError("resident session batch quota exhausted")
            if isinstance(prompts, (str, bytes)) or not 2 <= len(prompts) <= p.slots:
                raise ValueError("2..slots independent prompts required")
            if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= min(8192, p.context_per_slot-1):
                raise ValueError("invalid generation token limit")
            if type(seed) is not int or not 0 <= seed < 2**32-1:
                raise ValueError("explicit deterministic uint32 seed required")
            self._assert_source()
            deadline = min(self._deadline, time.monotonic() + p.timeout_seconds)
            tokenized = [self._tokenize(prompt, deadline) for prompt in prompts]
            if any(len(tokens) + max_new_tokens > p.context_per_slot for tokens in tokenized):
                raise ValueError("native tokenized prompt exceeds private slot context")
            barrier = threading.Barrier(len(prompts))
            def one(tokens):
                barrier.wait(timeout=max(0.01, deadline-time.monotonic()))
                row = self._call("/completion", {"prompt": tokens, "n_predict": max_new_tokens,
                    "seed": seed, "temperature": 0.0, "stream": False,
                    "cache_prompt": False, "return_tokens": True}, deadline=deadline)
                if not isinstance(row, dict) or row.get("truncated") is not False or row.get("stop_type") not in {"eos","limit","word"}:
                    raise LlamaCppRuntimeError("resident completion was incomplete or truncated")
                output, ids = row.get("content"), row.get("tokens")
                if (not isinstance(output, str) or not isinstance(ids, list)
                    or len(ids) > max_new_tokens or any(type(t) is not int or not 0 <= t <= 2**31-1 for t in ids)):
                    raise LlamaCppRuntimeError("invalid native completion payload")
                return {"text": output, "token_ids": ids, "stop_type": row["stop_type"],
                        "input_tokens": len(tokens)}
            executor = ThreadPoolExecutor(max_workers=len(prompts))
            futures = [executor.submit(one, tokens) for tokens in tokenized]
            try:
                _, pending = wait(futures, timeout=max(0, deadline-time.monotonic()))
                if pending:
                    raise TimeoutError("native batch deadline exceeded")
                rows = [future.result() for future in futures]
                self._assert_source()
                self._batches += 1
                return {"model_sha256": self._model.model_digest, "server_sha256": self._server.sha256,
                        "offloaded_layers_reported": list(self._offloaded), "slots": p.slots,
                        "logical_memory_estimate_bytes": self._estimate, "results": rows,
                        "status": "native_server_batch_completed_not_hardware_qualified"}
            except BaseException:
                self.close()
                raise
            finally:
                executor.shutdown(wait=True, cancel_futures=True)

    def close(self):
        with self._lock:
            self._closed = True
            self._ready.clear()
            if self._proc is not None:
                LlamaCppModel._terminate(self._proc)
                self._proc.wait()
            if self._reader is not None:
                self._reader.join(timeout=2)
            if self._temp is not None:
                self._temp.cleanup()
            self._logs.clear()
            self._key = None

    def __exit__(self, *args):
        self.close()
