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
import stat
import sys
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
    slot_spill_bytes: int = 0
    prefill_threads: int | None = None
    numa: str | None = None
    split_mode: str | None = None
    tensor_split: tuple[int, ...] = ()
    main_gpu: int | None = None
    cpu_moe_layers: int = 0
    moe_cache_mib: int = 0
    cpu_ffn_layers: int = 0

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
        if type(self.slot_spill_bytes) is not int or not 0 <= self.slot_spill_bytes <= 64*1024**3:
            raise ValueError("native slot spill ceiling outside bounds")
        if self.slots * self.context_per_slot > 1_048_576:
            raise ValueError("aggregate native context exceeds ceiling")
        if self.microbatch_tokens > self.batch_tokens or self.flash_attention not in {"auto", "on", "off"}:
            raise ValueError("invalid native kernel/batch policy")
        for value, minimum, maximum in ((self.prefill_threads, 1, 4096), (self.main_gpu, 0, 63)):
            if value is not None and (type(value) is not int or not minimum <= value <= maximum):
                raise ValueError("native topology value outside bounds")
        if self.numa not in (None, "distribute", "isolate", "numactl"):
            raise ValueError("invalid native NUMA policy")
        if self.split_mode not in (None, "none", "layer", "row"):
            raise ValueError("unqualified native tensor split mode")
        if type(self.tensor_split) is not tuple or len(self.tensor_split) > 16 or any(
                type(weight) is not int or not 1 <= weight <= 10000 for weight in self.tensor_split):
            raise ValueError("bounded positive integer GPU split weights required")
        if self.tensor_split and (len(self.tensor_split) < 2 or self.split_mode not in ("layer", "row")):
            raise ValueError("GPU weights require explicit multi-device split mode")
        if self.main_gpu is not None and self.split_mode not in ("none", "row"):
            raise ValueError("main GPU requires an explicit compatible split mode")
        if self.tensor_split and self.main_gpu is not None and self.main_gpu >= len(self.tensor_split):
            raise ValueError("main GPU is outside configured split")
        for value, maximum in ((self.cpu_moe_layers, 4096), (self.cpu_ffn_layers, 4096),
                               (self.moe_cache_mib, 65536)):
            if type(value) is not int or not 0 <= value <= maximum:
                raise ValueError("native expert/FFN placement outside bounds")
        if self.cpu_moe_layers and self.cpu_ffn_layers:
            raise ValueError("dense and MoE offload policies are mutually exclusive")
        if self.moe_cache_mib and not self.cpu_moe_layers:
            raise ValueError("expert cache requires explicit host expert placement")

    def tuning_args(self) -> tuple[str, ...]:
        """Construct only typed local placement switches, never arbitrary argv."""
        args = []
        for value, flag in ((self.prefill_threads, "--threads-batch"),
                            (self.numa, "--numa"), (self.split_mode, "--split-mode"),
                            (self.main_gpu, "--main-gpu")):
            if value is not None:
                args.extend((flag, str(value)))
        if self.tensor_split:
            args.extend(("--tensor-split", ",".join(map(str, self.tensor_split))))
        for value, flag in ((self.cpu_moe_layers, "--n-cpu-moe"),
                            (self.moe_cache_mib, "--moe-cache-mib"),
                            (self.cpu_ffn_layers, "--n-cpu-ffn")):
            if value:
                args.extend((flag, str(value)))
        return tuple(args)


class ResidentGGUFBatch:
    """One explicitly owned native process, multiple bounded local batch calls."""

    def __init__(self, model: LlamaCppModel, server: Path, server_sha256: str,
                 policy: ResidentBatchPolicy, *, runtime_libraries=(), spill_root: Path | None = None):
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
        geometry = model.serving_metadata
        kv = max(geometry.kv_bytes_per_token_upper_bound or 0, model.config.kv_bytes_per_token or 0)
        if geometry.architecture not in {"llama", "qwen2", "qwen2moe"} and model.config.kv_bytes_per_token is None:
            raise ValueError("nonuniform or unknown attention requires explicit reviewed KV byte ceiling")
        if not kv:
            raise ValueError("resident batch requires known conservative KV geometry")
        # Unknown architectures do not gain placement privileges. The model
        # metadata remains the authority; operator flags cannot enlarge ceilings.
        if policy.cpu_moe_layers and geometry.architecture != "qwen2moe":
            raise ValueError("host expert placement requires a reviewed MoE architecture")
        if policy.cpu_ffn_layers and geometry.architecture not in {"llama", "qwen2"}:
            raise ValueError("host dense FFN placement requires a reviewed dense architecture")
        if policy.cpu_moe_layers > policy.gpu_layers or policy.cpu_ffn_layers > policy.gpu_layers:
            raise ValueError("requested host placement exceeds the GPU layer envelope")
        if policy.prefill_threads is not None:
            available = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()
            if available is None or policy.prefill_threads > available:
                raise ValueError("prefill threads exceed available CPU affinity")
        self._estimate = model.total_model_bytes + model.config.runtime_scratch_bytes + (
            policy.slots * policy.context_per_slot * kv) + policy.moe_cache_mib * 1024**2
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
        self._guarded_owner = None
        self._watchdog = None
        self._spill_root = spill_root
        if bool(policy.slot_spill_bytes) != (spill_root is not None):
            raise ValueError("native spill root and byte ceiling must be supplied together")
        self._spill_temp = None
        self._disk_temp = None
        self._live_slots = set()
        self._spilled = {}

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
        if endpoint not in {"/health", "/tokenize", "/detokenize", "/completion"}:
            slot = re.fullmatch(r"/slots/([0-9]+)\?action=(save|restore|erase)", endpoint)
            if not self._spill_temp or not slot or not 0 <= int(slot.group(1)) < self._policy.slots:
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
            peer = connection.sock
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
                if response.isclosed():
                    break
                if peer is not None:
                    peer.settimeout(remaining)
                chunk = response.read1(min(65536, _MAX_REPLY_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > _MAX_REPLY_BYTES:
                    raise LlamaCppRuntimeError("native response exceeded byte ceiling")
            if response.length not in (None, 0):
                raise LlamaCppRuntimeError("native response body ended before declared length")
            value = json.loads(raw, object_pairs_hook=_strict_object, parse_constant=_bad_constant)
            if time.monotonic() >= min(deadline, self._deadline):
                raise TimeoutError("resident response deadline")
            return value
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
            args.extend(p.tuning_args())
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
                if p.slot_spill_bytes:
                    self._prepare_spill()
                    args[args.index("--no-slots")] = "--slots"
                    args[args.index("--no-cache-prompt")] = "--cache-prompt"
                    args += ["--slot-save-path", self._spill_temp.name + "/"]
                    # Native save files are hard-limited before exec. The
                    # wrapper is static and the child PID survives exec.
                    args = [sys.executable, "-I", "-c",
                            "import os,resource,sys;n=int(sys.argv[1]);resource.setrlimit(resource.RLIMIT_FSIZE,(n,n));os.execv(sys.argv[2],sys.argv[2:])",
                            str(p.slot_spill_bytes), *args]
                self._proc = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=root,
                    env={"PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root),
                         "LANG": "C", "LC_ALL": "C"},
                    start_new_session=True, close_fds=True, umask=0o077,
                    pass_fds=gguf_child_pass_fds())
                self._watchdog = threading.Timer(max(0, self._deadline-time.monotonic()),
                                                  LlamaCppModel._terminate, args=(self._proc,))
                self._watchdog.daemon = True
                self._watchdog.start()
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

    def generate(self, prompts: Sequence[str], *, max_new_tokens: int, seed: int = 0,
                 reuse_cache: bool = False):
        """Submit independent requests concurrently to the same native scheduler."""
        with self._lock:
            if not self._ready.is_set() or self._closed:
                raise RuntimeError("resident batch requires entered session")
            if self._guarded_owner is not None:
                raise RuntimeError("guarded resident session cannot accept operator batch calls")
            p = self._policy
            if self._batches >= p.max_batches:
                raise RuntimeError("resident session batch quota exhausted")
            if isinstance(prompts, (str, bytes)) or not 2 <= len(prompts) <= p.slots:
                raise ValueError("2..slots independent prompts required")
            if type(max_new_tokens) is not int or not 1 <= max_new_tokens <= min(8192, p.context_per_slot-1):
                raise ValueError("invalid generation token limit")
            if type(seed) is not int or not 0 <= seed < 2**32-1:
                raise ValueError("explicit deterministic uint32 seed required")
            if type(reuse_cache) is not bool or (reuse_cache and not self._spill_temp):
                raise ValueError("cache reuse requires explicit private slot spill mode")
            if self._spill_temp and any(i in self._spilled for i in range(len(prompts))):
                raise RuntimeError("restore or discard a spilled slot before reuse")
            self._assert_source()
            deadline = min(self._deadline, time.monotonic() + p.timeout_seconds)
            # Overlap private native tokenization without bypassing slot budgets.
            with ThreadPoolExecutor(max_workers=len(prompts)) as token_workers:
                tokenized = list(token_workers.map(lambda prompt: self._tokenize(prompt, deadline), prompts))
            if time.monotonic() >= deadline:
                raise TimeoutError("resident tokenization deadline exceeded")
            if any(len(tokens) + max_new_tokens > p.context_per_slot for tokens in tokenized):
                raise ValueError("native tokenized prompt exceeds private slot context")
            barrier = threading.Barrier(len(prompts))
            def one(index, tokens):
                barrier.wait(timeout=max(0.01, deadline-time.monotonic()))
                payload = {"prompt": tokens, "n_predict": max_new_tokens,
                    "seed": seed, "temperature": 0.0, "stream": False,
                    "cache_prompt": reuse_cache, "return_tokens": True}
                if self._spill_temp:
                    payload["id_slot"] = index
                row = self._call("/completion", payload, deadline=deadline)
                if not isinstance(row, dict) or row.get("truncated") is not False or row.get("stop_type") not in {"eos","limit","word"}:
                    raise LlamaCppRuntimeError("resident completion was incomplete or truncated")
                output, ids = row.get("content"), row.get("tokens")
                if (not isinstance(output, str) or not isinstance(ids, list)
                    or len(ids) > max_new_tokens or any(type(t) is not int or not 0 <= t <= 2**31-1 for t in ids)):
                    raise LlamaCppRuntimeError("invalid native completion payload")
                return {"text": output, "token_ids": ids, "stop_type": row["stop_type"],
                        "input_tokens": len(tokens), "slot": index if self._spill_temp else None}
            executor = ThreadPoolExecutor(max_workers=len(prompts))
            futures = [executor.submit(one, index, tokens) for index, tokens in enumerate(tokenized)]
            try:
                _, pending = wait(futures, timeout=max(0, deadline-time.monotonic()))
                if pending:
                    raise TimeoutError("native batch deadline exceeded")
                rows = [future.result() for future in futures]
                self._assert_source()
                self._batches += 1
                if self._spill_temp:
                    self._live_slots.update(range(len(rows)))
                return {"model_sha256": self._model.model_digest, "server_sha256": self._server.sha256,
                        "offloaded_layers_reported": list(self._offloaded), "slots": p.slots,
                        "logical_memory_estimate_bytes": self._estimate, "results": rows,
                        "native_tuning_args": list(p.tuning_args()),
                        "status": "native_server_batch_completed_not_hardware_qualified"}
            except BaseException:
                self.close()
                raise
            finally:
                executor.shutdown(wait=True, cancel_futures=True)

    def _prepare_spill(self):
        # Native serialization writes plaintext only into Linux tmpfs. That
        # tmpfs may itself swap: operators requiring no plaintext swap must
        # disable swap or use encrypted swap. Disk output is AES-GCM sealed.
        from .gguf_bundle import _open_directory
        mount = Path("/dev/shm")
        entries = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
        if not any(line.split(" - ", 1)[0].split()[4] == "/dev/shm"
                   and line.split(" - ", 1)[1].split()[0] == "tmpfs"
                   for line in entries if " - " in line):
            raise OSError("verified /dev/shm tmpfs required for slot spill")
        root = Path(os.path.abspath(os.fspath(self._spill_root)))
        fd = _open_directory(root)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise PermissionError("native spill root must be owner-private")
        finally:
            os.close(fd)
        self._spill_temp = tempfile.TemporaryDirectory(prefix="skkv-", dir=mount)
        self._disk_temp = tempfile.TemporaryDirectory(prefix=".skkv-", dir=root)

    @staticmethod
    def _private_file(path, *, writing=False):
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL) if writing else (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or (not writing and info.st_mode & 0o022)):
            os.close(fd)
            raise PermissionError("native spill file custody rejected")
        return os.fdopen(fd, "wb" if writing else "rb")

    def _spill_transfer(self, source, destination, *, key, slot, size, encrypt):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        cipher = AESGCM(key)
        chunk = 1024**2
        with self._private_file(source) as reader, self._private_file(destination, writing=True) as writer:
            before = os.fstat(reader.fileno())
            expected = size if encrypt else size + 28 * ((size+chunk-1)//chunk)
            if before.st_size != expected:
                raise OSError("native spill length changed")
            for offset in range(0, size, chunk):
                if time.monotonic() >= self._deadline:
                    raise TimeoutError("native slot transfer deadline")
                count = min(chunk, size-offset)
                aad = f"{self._model.model_digest}:{slot}:{offset}:{count}".encode("ascii")
                raw = reader.read(count if encrypt else count+28)
                if len(raw) != (count if encrypt else count+28):
                    raise OSError("native spill transfer truncated")
                if encrypt:
                    nonce = secrets.token_bytes(12)
                    writer.write(nonce + cipher.encrypt(nonce, raw, aad))
                else:
                    writer.write(cipher.decrypt(raw[:12], raw[12:], aad))
            if reader.read(1):
                raise OSError("native spill trailing bytes")
            after = os.fstat(reader.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise OSError("native spill source changed during transfer")
            writer.flush()
            os.fsync(writer.fileno())

    def spill_slot(self, slot: int):
        """Serialize native GGUF KV, seal to disk, erase the resident slot.

        Erase frees sequence capacity; llama.cpp can retain preallocated GPU
        backing buffers. This does not promise a driver VRAM decrease.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        with self._lock:
            if not self._ready.is_set() or not self._spill_temp or type(slot) is not int or slot not in self._live_slots:
                raise RuntimeError("completed private native slot required")
            if slot in self._spilled:
                raise RuntimeError("slot already spilled")
            self._assert_source()
            cap = self._policy.slot_spill_bytes
            existing = sum(row["sealed_bytes"] for row in self._spilled.values())
            if existing >= cap:
                raise MemoryError("native encrypted spill budget exhausted")
            root = Path(self._spill_temp.name)
            available = os.statvfs(root)
            if available.f_bavail * available.f_frsize < cap-existing:
                raise MemoryError("insufficient tmpfs spill capacity")
            name = secrets.token_hex(24) + ".bin"
            plain, sealed = root/name, Path(self._disk_temp.name)/(name+".sealed")
            deadline = min(self._deadline, time.monotonic()+self._policy.timeout_seconds)
            try:
                result = self._call(f"/slots/{slot}?action=save", {"filename": name}, deadline=deadline)
                size, tokens = result.get("n_written"), result.get("n_saved")
                if (result.get("id_slot") != slot or result.get("filename") != name
                        or type(size) is not int or type(tokens) is not int
                        or not 1 <= size <= cap or not 1 <= tokens <= self._policy.context_per_slot):
                    raise LlamaCppRuntimeError("native slot save receipt rejected")
                sealed_size = size + 28*((size+1024**2-1)//1024**2)
                if existing+sealed_size > cap:
                    raise MemoryError("native spill exceeds remaining encrypted budget")
                key = AESGCM.generate_key(bit_length=256)
                self._spill_transfer(plain, sealed, key=key, slot=slot, size=size, encrypt=True)
                plain.unlink()
                erased = self._call(f"/slots/{slot}?action=erase", {}, deadline=deadline)
                if erased.get("id_slot") != slot or erased.get("n_erased") != tokens:
                    raise LlamaCppRuntimeError("native slot erase not confirmed")
                self._assert_source()
                self._spilled[slot] = {"path": sealed, "key": key, "bytes": size,
                                       "sealed_bytes": sealed_size, "tokens": tokens}
                self._live_slots.remove(slot)
                return {"slot": slot, "native_tokens_saved_and_erased": tokens,
                        "encrypted_bytes": sealed_size, "physical_gpu_allocation_reclaimed": False}
            except BaseException:
                self.close()
                raise
            finally:
                plain.unlink(missing_ok=True)

    def restore_slot(self, slot: int):
        """Restore a same-process, same-model encrypted native slot."""
        with self._lock:
            if not self._ready.is_set() or type(slot) is not int or slot not in self._spilled:
                raise RuntimeError("unknown private native spill slot")
            if slot in self._live_slots:
                raise RuntimeError("cannot overwrite an active native slot")
            row = self._spilled[slot]
            self._assert_source()
            name = secrets.token_hex(24)+".bin"
            plain = Path(self._spill_temp.name)/name
            deadline = min(self._deadline, time.monotonic()+self._policy.timeout_seconds)
            try:
                self._spill_transfer(row["path"], plain, key=row["key"], slot=slot,
                                     size=row["bytes"], encrypt=False)
                restored = self._call(f"/slots/{slot}?action=restore", {"filename": name}, deadline=deadline)
                if (restored.get("id_slot") != slot or restored.get("filename") != name
                        or restored.get("n_restored") != row["tokens"] or restored.get("n_read") != row["bytes"]):
                    raise LlamaCppRuntimeError("native slot restore receipt rejected")
                self._assert_source()
                row["path"].unlink()
                del self._spilled[slot]
                self._live_slots.add(slot)
                return {"slot": slot, "native_tokens_restored": row["tokens"],
                        "native_bytes_read": row["bytes"]}
            except BaseException:
                self.close()
                raise
            finally:
                plain.unlink(missing_ok=True)

    def discard_slot_spill(self, slot: int):
        with self._lock:
            if type(slot) is not int or slot not in self._spilled:
                raise RuntimeError("unknown native spill slot")
            self._spilled[slot]["path"].unlink()
            del self._spilled[slot]

    def close(self):
        with self._lock:
            self._closed = True
            self._ready.clear()
            if self._watchdog is not None:
                self._watchdog.cancel()
            if self._proc is not None:
                LlamaCppModel._terminate(self._proc)
                self._proc.wait()
            if self._reader is not None:
                self._reader.join(timeout=2)
            if self._temp is not None:
                self._temp.cleanup()
            if self._spill_temp is not None:
                self._spill_temp.cleanup()
            if self._disk_temp is not None:
                self._disk_temp.cleanup()
            self._spilled.clear()
            self._live_slots.clear()
            self._logs.clear()
            self._key = None

    def __exit__(self, *args):
        self.close()
