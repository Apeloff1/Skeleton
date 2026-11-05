"""Exact-identity GGUF backend with killable, separately-owned computation.

No model runs in the HTTP or durable database process. Native timeouts close
and poison the child; the durable job is left pending for explicit inspection.
An unknown result is NEVER replayed through a second worker automatically.
"""
from __future__ import annotations
from pathlib import Path
import threading
import time
from .contracts import (IsolationPolicy, IsolationUnavailable,
                        IsolationProtocolError)
from .wire import read_frame, write_frame
from .messages import validate
from .receipts import parse_ready, parse_generation
from .process import OwnedWorker
from .resource_gate import require_headroom
from ..gguf.manifest import GGUFModelManifest


class IsolatedGGUFBackend:
    def __init__(self, model_root: Path | str, manifest: GGUFModelManifest, *,
                 n_ctx: int = 2048, n_threads: int = 4, n_gpu_layers: int = 0,
                 startup_ms: int = 180000, inference_ms: int = 120000,
                 capacity_lease=None,
                 ) -> None:
        if not isinstance(manifest, GGUFModelManifest):
            raise IsolationProtocolError('approved GGUF manifest is required')
        self.policy = IsolationPolicy(context_tokens=n_ctx, threads=n_threads,
             gpu_layers=n_gpu_layers, startup_ms=startup_ms, inference_ms=inference_ms)
        if n_ctx > manifest.context_ceiling or n_gpu_layers > manifest.gpu_layers_ceiling:
            raise IsolationProtocolError('requested isolation exceeds approved manifest limits')
        root = Path(model_root)
        if not root.is_absolute():
            raise IsolationProtocolError('model root must be absolute')
        if capacity_lease is not None:
            from ..admission.broker import ModelCapacityLease
            if (not isinstance(capacity_lease,ModelCapacityLease)
                    or not capacity_lease.active
                    or capacity_lease._entry['reservation']['model_sha256']!=manifest.model_sha256):
                raise IsolationProtocolError('native child cannot inherit unbound capacity')
            capacity_lease.assert_live()
        self._lock = threading.RLock()
        # A generation owns the IPC stream; shutdown must NOT wait for it.
        self._turn_lock = threading.Lock()
        self._poisoned = False
        self._next = 0
        self._started_ns = time.monotonic_ns()
        self._minimum_memory_reserve = 128 * 1024 * 1024
        self._requests_completed = 0
        self._request_failures = 0
        self._worker = (OwnedWorker(retained_fds=(capacity_lease.fd,))
                        if capacity_lease is not None else OwnedWorker())
        try:
            until = time.monotonic_ns() + startup_ms * 1_000_000
            boot = {'version': 1, 'type': 'boot', 'model_root': str(root),
                    'manifest_name': 'model.manifest.json',
                    'context_tokens': n_ctx, 'threads': n_threads,
                    'gpu_layers': n_gpu_layers,
                    'model_sha256': manifest.model_sha256,
                    'manifest_sha256': manifest.manifest_digest,
                    'request_timeout_ms': inference_ms,
                    'max_frame_bytes': self.policy.max_frame_bytes}
            write_frame(self._worker.write_fd, boot, until, 16384)
            ready = read_frame(self._worker.read_fd, until, 16384)
            self._tokenizer_digest = parse_ready(ready, model=manifest.model_sha256,
                                                manifest=manifest.manifest_digest)
            # For GGUF the embedded tokenizer is bound to the exact model bytes.
            if self._tokenizer_digest != manifest.model_sha256:
                raise IsolationProtocolError('native tokenizer identity not model-bound')
            self._model_digest = manifest.model_sha256
            self._manifest_digest = manifest.manifest_digest
        except BaseException:
            self._poisoned = True
            self._worker.stop(grace_ms=0)
            raise

    @property
    def model_digest(self) -> str:
        return self._model_digest

    @property
    def tokenizer_digest(self) -> str:
        return self._tokenizer_digest

    @property
    def healthy(self) -> bool:
        with self._lock:
            return not self._poisoned and self._worker.alive()

    def health(self) -> dict:
        # Never include private source paths, prompts, model output or secrets.
        with self._lock:
            return {'status': 'running' if self.healthy else 'held',
                    'model_sha256': self._model_digest, 'tokenizer_sha256': self._tokenizer_digest,
                    'manifest_sha256': self._manifest_digest,
                    'requests_completed': self._requests_completed,
                    'requests_failed': self._request_failures,
                    'uptime_ns': max(0, time.monotonic_ns() - self._started_ns),
                    'isolation': 'dedicated-local-child-no-provider'}

    def _begin(self) -> int:
        with self._lock:
            if self._poisoned or not self._worker.alive():
                self._poisoned = True
                raise IsolationUnavailable('native worker no longer available')
            self._next += 1
            return self._next

    def _fault(self) -> None:
        with self._lock:
            self._request_failures += 1
            self._poisoned = True
            self._worker.stop(grace_ms=0)

    def admit_before_reservation(self) -> dict:
        """Conservative OS resource check before claiming durable inference.

        Unlike generate(), this performs no model work and consumes no IPC
        sequence. A rejected request therefore has no pending execution lease.
        """
        with self._lock:
            if self._poisoned or not self._worker.alive():
                raise IsolationUnavailable('native worker not ready for admission')
            return require_headroom(self._minimum_memory_reserve)

    def probe(self, *, deadline_ms: int = 2000) -> dict:
        """Prove worker responsiveness, never model quality.

        The IPC lock serializes messages. Independent close() must be able to
        terminate a stalled worker without waiting for model computation.
        """
        if type(deadline_ms) is not int or not 100 <= deadline_ms <= 30000:
            raise IsolationProtocolError('invalid heartbeat deadline')
        with self._turn_lock:
            seq = self._begin()
            deadline = time.monotonic_ns() + deadline_ms * 1_000_000
            try:
                write_frame(self._worker.write_fd,
                            {'version': 1, 'type': 'ping', 'request': seq}, deadline, 16384)
                result = read_frame(self._worker.read_fd, deadline, 16384)
                if (not isinstance(result, dict) or set(result) !=
                    {'version', 'type', 'request', 'model_sha256'}
                    or type(result['version']) is not int or result['version'] != 1
                    or result['type'] != 'pong' or type(result['request']) is not int
                    or result['request'] != seq or result['model_sha256'] != self._model_digest):
                    raise IsolationProtocolError('native worker heartbeat identity changed')
                with self._lock:
                    if self._poisoned or not self._worker.alive():
                        raise IsolationUnavailable('worker closed during heartbeat')
            except BaseException:
                self._fault()
                raise
            return {'status': 'protocol-responsive-not-generation-qualified',
                    'model_sha256': self._model_digest, 'request': seq}

    def generate(self, messages: list[dict[str, str]], *,
                 max_output_tokens: int, seed: int, temperature: float):
        # Only one command may own a pipe at once. close() is independent and
        # can terminate the child to interrupt a native C++ hang.
        with self._turn_lock:
            normalized = validate(messages, max_output_tokens, seed, temperature, self.policy)
            seq = self._begin()
            deadline = time.monotonic_ns() + self.policy.inference_ms * 1_000_000
            try:
                write_frame(self._worker.write_fd, {'version': 1, 'type': 'generate',
                    'request': seq, 'messages': normalized,
                    'max_output_tokens': max_output_tokens,
                    'seed': seed, 'temperature': float(temperature)},
                    deadline, self.policy.max_frame_bytes)
                reply = read_frame(self._worker.read_fd, deadline, self.policy.max_frame_bytes)
                result = parse_generation(reply, request=seq, model=self._model_digest,
                    tokenizer=self._tokenizer_digest, max_tokens=max_output_tokens,
                    context_tokens=self.policy.context_tokens)
                with self._lock:
                    if self._poisoned or not self._worker.alive():
                        raise IsolationUnavailable('native process closed before accepting receipt')
                    self._requests_completed += 1
            except BaseException:
                self._fault()
                raise
            return result

    def close(self) -> None:
        # Intentional absence of _turn_lock: otherwise a stuck model call would
        # prevent an independent shutdown/cancellation from killing the worker.
        with self._lock:
            self._poisoned = True
            self._worker.stop(grace_ms=self.policy.shutdown_ms)

    def __enter__(self) -> 'IsolatedGGUFBackend':
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
