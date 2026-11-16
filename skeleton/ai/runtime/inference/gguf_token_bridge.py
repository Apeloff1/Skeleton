"""Exact-token GGUF worker, distinct from approximate llama-cli admission."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import subprocess
import threading
import time
from dataclasses import replace

from .llama_cpp import LlamaCppConfig, LlamaCppModel, LlamaCppRuntimeError, _digest
from .lease_custody import gguf_child_pass_fds
from .gguf_private_transport import private_frame, linux_descriptor_custody
from .local import (
    LocalInferenceCancelled, LocalInferenceEngine, LocalInferenceRequest,
    LocalInferenceResult, LocalPreparedInput,
)

BRIDGE_RUNTIME_KIND = "llama.cpp-token-bridge-v1"
_MAGIC = b"SKG1"
_MAX_TEXT = 4 * 1024 * 1024
_MAX_TOKENS = 1_048_576
_MAX_FRAME = 2 * _MAX_TEXT + 8192 * 4 + 64


def _fail(message="GGUF bridge protocol rejected"):
    return LlamaCppRuntimeError(message)


def _ids(sequence):
    if type(sequence) not in (tuple, list) or len(sequence) > _MAX_TOKENS:
        raise _fail()
    if any(type(token) is not int or not 0 <= token < 2**31 for token in sequence):
        raise _fail()
    return tuple(sequence)


def _pack_ids(sequence):
    tokens = _ids(sequence)
    return struct.pack("<I", len(tokens)) + struct.pack("<" + "I" * len(tokens), *tokens)


def _text(raw):
    if type(raw) is not bytes or len(raw) > _MAX_TEXT:
        raise _fail()
    return struct.pack("<I", len(raw)) + raw


class _Frame:
    def __init__(self, raw):
        if type(raw) is not bytes or not 4 <= len(raw) <= _MAX_FRAME or raw[:4] != _MAGIC:
            raise _fail()
        self.raw, self.offset = raw, 4

    def number(self):
        if self.offset + 4 > len(self.raw):
            raise _fail()
        num = struct.unpack_from("<I", self.raw, self.offset)[0]
        self.offset += 4
        return num

    def ids(self, limit=_MAX_TOKENS):
        count = self.number()
        end = self.offset + count * 4
        if count > limit or end > len(self.raw):
            raise _fail()
        values = struct.unpack_from("<" + "I" * count, self.raw, self.offset)
        self.offset = end
        return _ids(values)

    def text(self, limit=_MAX_TEXT):
        count = self.number()
        end = self.offset + count
        if count > limit or end > len(self.raw):
            raise _fail()
        try:
            value = self.raw[self.offset:end].decode("utf-8", "strict")
        except UnicodeError:
            raise _fail("GGUF bridge response is not valid UTF-8") from None
        self.offset = end
        return value

    def finish(self):
        if self.offset != len(self.raw):
            raise _fail()


def _compatible(config):
    if (type(config) is not LlamaCppConfig or config.gpu_layers not in (0, None)
            or config.temperature != 0 or config.extra_args or config.output_framing != "raw"
            or not config.reject_model_symlink or config.environment
            or config.runtime_libraries
            or config.kv_cache_location != "backend"
            or config.kv_cache_type_k is not None or config.kv_cache_type_v is not None
            or config.context_size is None or (config.threads or 1) > 256
            or (config.batch_size or 128) > 8192):
        raise _fail("exact GGUF bridge requires explicit CPU greedy raw profile")


class GgufTokenBridgeModel(LlamaCppModel):
    """One pinned executable and GGUF own encoding, decoding and generation."""
    protocol_capabilities = ("text-generation",)
    tokenizer_kind = "native_tokenizer"
    requires_exact_guard_tokens = True

    def __init__(self, config):
        if os.name != "posix":
            raise _fail("exact GGUF bridge requires POSIX process custody")
        _compatible(config)
        super().__init__(replace(config, rehash_artifacts_each_run=True))
        self._issuer = object()
        self._worker_lock = threading.Lock()
        self._tokenizer_digest = _digest({
            "schema": "skeleton.gguf.exact-tokenizer.v1", "model": self.model_digest,
            "runtime": self.runtime_digest, "add_special": False, "parse_special": False,
            "remove_special": False, "unparse_special": False,
        })

    @property
    def tokenizer_digest(self):
        return self._tokenizer_digest

    @property
    def execution_profile_digest(self):
        return _digest({"base": super().execution_profile_digest,
                        "protocol": BRIDGE_RUNTIME_KIND, "tokenizer": self.tokenizer_digest})

    def assert_identity(self):
        _compatible(self.config)
        if not self.config.rehash_artifacts_each_run:
            raise _fail("exact GGUF full artifact admission disabled")
        from skeleton.context.pre_delivery_guard import native_verification_cancel_event
        event = native_verification_cancel_event()
        def interrupt():
            if event is not None and event.is_set():
                raise LocalInferenceCancelled("exact GGUF identity verification cancelled")
        self._assert_artifacts_stable(interrupt=interrupt)

    def activate_prelaunch_resource_profile(self, profile):
        _compatible(profile)
        super().activate_prelaunch_resource_profile(profile)

    def _effective_environment(self):
        # No ambient dynamic-loader or GPU overrides for the CPU-only bridge.
        return {k: v for k, v in super()._effective_environment().items() if k in ("PATH", "OMP_NUM_THREADS")}

    def execution_snapshot(self):
        result = super().execution_snapshot()
        result.update(token_transport_kind=BRIDGE_RUNTIME_KIND,
                      exact_token_admission=True, cpu_only=True,
                      private_transport=("linux_sealed_memfd" if linux_descriptor_custody() else "posix_named_private_file"),
                      immutable_storage_verified=False)
        return result

    def generation_limits(self):
        result = super().generation_limits()
        result.update(tokenizer=self.tokenizer_kind, tokenizer_max_chars=_MAX_TEXT,
                      tokenizer_max_tokens=min(_MAX_TOKENS, result["max_total_tokens"]))
        return result

    def _render_prompt(self, request):
        return request.rendered_input

    def _request_bytes(self, request):
        # Provider adapter uses 1.0 as its historical default; the admitted
        # deployment profile is explicitly greedy, just like its CLI profile.
        if (not isinstance(request, LocalInferenceRequest) or request.tools
                or request.structured_output_schema is not None or request.stop
                or request.temperature not in (0.0, 1.0) or request.top_k != 0
                or request.top_p != 1.0 or request.min_p != 0.0
                or request.repetition_penalty != 1.0):
            raise _fail("exact GGUF bridge supports only its fixed greedy text profile")
        try:
            raw = request.rendered_input.encode("utf-8", "strict")
        except UnicodeError:
            raise _fail("invalid prompt encoding") from None
        if not 1 <= len(raw) <= _MAX_TEXT:
            raise _fail("GGUF bridge prompt exceeds bounds")
        return raw

    def _invoke(self, operation, payload, *, completion=0, cancel=None, deadline=None):
        if operation not in ("encode", "decode", "roundtrip", "generate") or len(payload) > _MAX_FRAME:
            raise _fail()
        from skeleton.context.pre_delivery_guard import native_verification_cancel_event
        guard_cancel = native_verification_cancel_event()
        cancel = cancel if cancel is not None else threading.Event()
        started = time.monotonic()
        limit = float(self.config.timeout_seconds)
        if operation != "generate":
            limit = min(limit, 20.0)
        if deadline is not None:
            limit = min(limit, deadline - started)

        def interrupt():
            if cancel.is_set() or (guard_cancel is not None and guard_cancel.is_set()):
                raise LocalInferenceCancelled("exact GGUF bridge cancelled")
            if time.monotonic() - started >= limit:
                raise TimeoutError("exact GGUF bridge deadline elapsed")

        while not self._worker_lock.acquire(timeout=0.05):
            interrupt()
        try:
            interrupt()
            _compatible(self.config)
            if not self.config.rehash_artifacts_each_run:
                raise _fail("exact GGUF artifact rehash required")
            # Freeze the resource profile before opening/hashing any artifacts.
            with self._process_lock:
                self._inference_admitted = True
                profile = self.execution_profile_digest
            if not linux_descriptor_custody():
                self._assert_artifacts_stable(interrupt=interrupt)
            else:
                self.check_readiness()
            with private_frame(self._runtime, self._model, _MAGIC + payload, interrupt) as frame:
                release, process = None, None
                with self._process_lock:
                    self._inference_admitted = True
                    self._spawning_processes += 1
                try:
                    guard = self._resource_preflight
                    if guard is not None:
                        with self._process_lock:
                            self._resource_preflight_checks += 1
                        guard()
                    factory = self._resource_lease_factory
                    if factory is not None:
                        release = factory()
                        if not callable(release):
                            raise _fail("native GGUF lease custody unavailable")
                    interrupt()
                    if self.execution_profile_digest != profile:
                        raise _fail("exact GGUF execution profile changed before launch")
                    frame.check_metadata()
                    process = subprocess.Popen(
                        [frame.executable, operation, frame.model, str(frame.source), str(frame.target),
                         str(self._effective_context()), str(self.config.threads or 1),
                         str(self.config.batch_size or 128), str(completion)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=frame.stderr,
                        cwd=frame.base, env=self._child_environment(frame.base), shell=False,
                        start_new_session=True, close_fds=True,
                        pass_fds=tuple(sorted(set(gguf_child_pass_fds() + frame.pass_fds))),
                    )
                    with self._process_lock:
                        self._active_processes.add(process.pid)
                        self._processes_started += 1
                finally:
                    with self._process_lock:
                        self._spawning_processes -= 1
                    if process is None and callable(release):
                        release()
                try:
                    while True:
                        interrupt()
                        output_size, stderr_size = frame.sizes()
                        if output_size > _MAX_FRAME or stderr_size > self.config.max_stderr_bytes:
                            raise _fail("GGUF bridge output exceeds bounded custody")
                        if process.poll() is not None:
                            break
                        time.sleep(0.025)
                    if process.returncode != 0:
                        raise _fail("GGUF bridge rejected native execution")
                    frame.verify(interrupt)
                    if not linux_descriptor_custody():
                        self._assert_artifacts_stable(interrupt=interrupt)
                    if self.execution_profile_digest != profile:
                        raise _fail("exact GGUF execution profile changed")
                    result = _Frame(frame.read(_MAX_FRAME))
                    interrupt()
                    return result
                finally:
                    with self._process_lock:
                        self._draining_processes.add(process.pid)
                        if process.poll() is None:
                            self._termination_requests += 1
                    try:
                        self._terminate(process)
                        process.wait()
                    finally:
                        with self._process_lock:
                            self._draining_processes.discard(process.pid)
                            self._active_processes.discard(process.pid)
                            self._processes_exited += 1
                        if callable(release):
                            release()
        except (OSError, UnicodeError):
            raise _fail("GGUF bridge transport unavailable") from None
        finally:
            self._worker_lock.release()

    def encode_ids(self, text):
        if type(text) is not str or len(text) > _MAX_TEXT:
            raise _fail()
        frame = self._invoke("encode", _text(text.encode("utf-8", "strict")))
        result = frame.ids()
        frame.finish()
        return result

    def decode_ids(self, tokens):
        frame = self._invoke("decode", _pack_ids(tokens))
        value = frame.text()
        frame.finish()
        return value

    def roundtrip_ids(self, text):
        """One vocabulary load for the exact token vector and byte echo."""
        if type(text) is not str or len(text) > _MAX_TEXT:
            raise _fail()
        frame = self._invoke("roundtrip", _text(text.encode("utf-8", "strict")))
        tokens, decoded = frame.ids(), frame.text()
        frame.finish()
        if decoded != text:
            raise _fail("exact GGUF prompt does not round-trip")
        return tokens, decoded

    def count_input_tokens(self, request):
        raw = self._request_bytes(request)
        return len(self.encode_ids(raw.decode("utf-8")))

    def prepare_input(self, request, *, scope_digest=None):
        raw = self._request_bytes(request)
        ids, decoded = self.roundtrip_ids(raw.decode("utf-8"))
        if not ids or decoded.encode("utf-8") != raw:
            raise _fail("exact GGUF prompt does not round-trip")
        if len(ids) + request.max_output_tokens > self._effective_context():
            raise _fail("exact GGUF context capacity exceeded")
        return LocalPreparedInput(
            request_digest=request.digest, model_digest=self.model_digest,
            runtime_digest=self.runtime_digest, execution_profile_digest=self.execution_profile_digest,
            tokenizer_digest=self.tokenizer_digest, source_digest=hashlib.sha256(raw).hexdigest(),
            sequence_digest=hashlib.sha256(_pack_ids(ids)).hexdigest(), input_tokens=len(ids),
            scope_digest=scope_digest, token_sequence=ids, issuer=self._issuer,
        )

    def validate_prepared_input(self, request, prepared):
        raw = self._request_bytes(request)
        if type(prepared) is not LocalPreparedInput or type(prepared.token_sequence) is not tuple:
            raise _fail("exact GGUF prepared input missing")
        prepared.assert_binding(
            request, issuer=self._issuer, model_digest=self.model_digest, runtime_digest=self.runtime_digest,
            execution_profile_digest=self.execution_profile_digest, tokenizer_digest=self.tokenizer_digest,
            source_digest=hashlib.sha256(raw).hexdigest(),
        )
        ids = _ids(prepared.token_sequence)
        if (not ids or len(ids) != prepared.input_tokens
                or hashlib.sha256(_pack_ids(ids)).hexdigest() != prepared.sequence_digest
                or len(ids) + request.max_output_tokens > self._effective_context()):
            raise _fail("exact GGUF prepared token custody changed")

    def infer(self, request, cancel):
        if cancel.is_set():
            raise LocalInferenceCancelled("exact GGUF generation cancelled")
        return self.infer_prepared(request, cancel, self.prepare_input(request))

    def infer_prepared(self, request, cancel, prepared):
        started = time.monotonic()
        deadline = started + float(self.config.timeout_seconds)
        self.validate_prepared_input(request, prepared)
        raw = self._request_bytes(request)
        ids = prepared.token_sequence
        frame = self._invoke("generate", _text(raw) + _pack_ids(ids),
                             completion=request.max_output_tokens, cancel=cancel, deadline=deadline)
        finish = frame.number()
        consumed = frame.ids()
        output_ids = frame.ids(request.max_output_tokens)
        output = frame.text(min(self.config.max_output_bytes, _MAX_TEXT))
        frame.finish()
        if (finish not in (0, 1) or consumed != ids
                or (finish == 1 and len(output_ids) != request.max_output_tokens)
                or (finish == 0 and len(output_ids) >= request.max_output_tokens)):
            raise _fail("physical GGUF token receipt mismatch")
        if cancel.is_set():
            raise LocalInferenceCancelled("exact GGUF generation cancelled")
        echo = self._invoke("decode", _pack_ids(output_ids), cancel=cancel, deadline=deadline)
        if echo.text() != output:
            raise _fail("physical GGUF output token echo mismatch")
        echo.finish()
        if time.monotonic() >= deadline:
            raise TimeoutError("exact GGUF overall generation deadline elapsed")
        if cancel.is_set():
            raise LocalInferenceCancelled("exact GGUF generation cancelled")
        receipt = _digest({"schema": "skeleton.gguf.exact-receipt.v1",
                           "model": self.model_digest, "runtime": self.runtime_digest,
                           "execution_profile": self.execution_profile_digest,
                           "tokenizer": self.tokenizer_digest, "request": request.digest,
                           "input_ids_sha256": prepared.sequence_digest,
                           "output_ids_sha256": hashlib.sha256(_pack_ids(output_ids)).hexdigest(),
                           "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                           "finish": finish})
        return LocalInferenceResult(
            text=output, model_id=self.model_id, model_digest=self.model_digest,
            input_tokens=len(ids), output_tokens=len(output_ids),
            finish_reason="length" if finish else "completed",
            response_id="gguf-exact:" + self.runtime_digest + ":" + self.model_digest + ":" + receipt,
            execution_receipt_digest=receipt, latency_ms=(time.monotonic()-started)*1000,
        )


def build_exact_gguf_adapter(config, *, cache_size=0, default_seed=0, max_concurrency=1,
                             max_queue_size=256, max_batch_size=256,
                             require_guarded_inference=False, guarded_components=None):
    from .guarded_composition import compose_protected_local_adapter, is_protected_component_source
    if require_guarded_inference is not True or not is_protected_component_source(guarded_components):
        raise _fail("exact GGUF bridge requires trusted protected inference")
    backend = GgufTokenBridgeModel(config)
    engine = LocalInferenceEngine(backend, cache_size=cache_size,
        max_concurrency=max_concurrency, max_queue_size=max_queue_size,
        max_batch_size=max_batch_size, require_guarded_context=True)
    return compose_protected_local_adapter(engine, components=guarded_components, default_seed=default_seed)
