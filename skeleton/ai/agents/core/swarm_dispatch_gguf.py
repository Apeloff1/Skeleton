"""Operator-pinned GGUF dispatch through the existing governed local runtime.

This adapter grants only an explicitly configured, single local CPU model.
It does not download models, construct executable commands, add a provider,
run model-selected tools, or attest the factual correctness of generated text.
The private host administrative boundary provisions all paths and policy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import time

from skeleton.automation.agents.swarm_durable import (
    DurableSwarmError, HostDispatchAttempt, HostTransportReply, HostWorkerReceipt,
    LocalSubprocessTransport, SQLiteWorkerCustody, _check_local_attempt,
    _wait_bytes, _wait_digest, _wait_identifier,
)

GGUF_OPERATION = "gguf_generate"
GGUF_CAPABILITY = "local-gguf"
_MAX_NATIVE_OUTPUT_BYTES = 8192
_SCHEMA = "skeleton.dispatch.gguf.v1"


def _native_hash(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _int(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DurableSwarmError("invalid pinned GGUF budget")
    return value


def _path(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 4096
            or any(ord(ch) < 32 for ch in value)
            or not Path(value).is_absolute() or str(Path(value)) != value
            or ".." in Path(value).parts):
        raise DurableSwarmError("GGUF policy requires absolute canonical asset paths")
    return value


def _trusted_file(path: str, *, executable: bool = False, private: bool = False) -> None:
    """Refuse mutable shared asset directories; the same-UID operator is trusted."""
    candidate = Path(path)
    if candidate.resolve(strict=True) != candidate:
        raise DurableSwarmError("GGUF asset symlink path refused")
    info = candidate.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022):
        raise DurableSwarmError("GGUF asset is not a trusted regular file")
    if private and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise DurableSwarmError("GGUF workspace anchor must be owner-private")
    if executable and not os.access(candidate, os.X_OK):
        raise DurableSwarmError("GGUF executable is not executable")
    for parent in candidate.parents:
        parent_info = parent.stat()
        if (not stat.S_ISDIR(parent_info.st_mode)
                or parent_info.st_uid not in (0, os.getuid())):
            raise DurableSwarmError("GGUF asset directory ownership refused")
        if parent_info.st_mode & 0o022 and not (
                parent_info.st_mode & stat.S_ISVTX and parent_info.st_uid in (0, os.getuid())):
            raise DurableSwarmError("GGUF asset directory allows untrusted replacement")


@dataclass(frozen=True, slots=True)
class PinnedGGUFPolicy:
    executable: str
    model: str
    runtime_sha256: str
    model_sha256: str
    context_tokens: int
    threads: int
    batch_tokens: int
    kv_bytes_per_token: int
    reserve_bytes: int
    timeout_seconds: int
    max_output_tokens: int
    runtime_libraries: tuple[tuple[str, str], ...]
    workspace_db: str | None
    execution_profile_sha256: str | None

    @classmethod
    def parse(cls, record: dict, *, provisioning: bool = False) -> PinnedGGUFPolicy:
        required = {"executable", "model", "runtime_sha256", "model_sha256", "context_tokens",
                    "threads", "batch_tokens", "kv_bytes_per_token", "reserve_bytes",
                    "timeout_seconds", "max_output_tokens", "runtime_libraries", "workspace_db"}
        fields = required if provisioning else required | {"execution_profile_sha256"}
        if type(record) is not dict or set(record) != fields:
            raise DurableSwarmError("invalid GGUF policy properties")
        context = _int(record["context_tokens"], 128, 131072)
        output = _int(record["max_output_tokens"], 1, min(2048, context // 2))
        libraries = record["runtime_libraries"]
        if type(libraries) is not list or len(libraries) > 128:
            raise DurableSwarmError("invalid runtime library pin inventory")
        parsed = []
        for entry in libraries:
            if (type(entry) is not list or len(entry) != 2
                    or type(entry[0]) is not str or not 1 <= len(entry[0]) <= 256
                    or Path(entry[0]).name != entry[0] or entry[0] in (".", "..")
                    or any(ord(ch) < 32 for ch in entry[0])):
                raise DurableSwarmError("invalid adjacent runtime library identity")
            parsed.append((entry[0], _wait_digest(entry[1])))
        if len({name for name, _ in parsed}) != len(parsed):
            raise DurableSwarmError("duplicate runtime library pin")
        return cls(
            _path(record["executable"]), _path(record["model"]),
            _wait_digest(record["runtime_sha256"]), _wait_digest(record["model_sha256"]),
            context, _int(record["threads"], 1, 256),
            _int(record["batch_tokens"], 1, min(8192, context)),
            _int(record["kv_bytes_per_token"], 1, 1024**3),
            _int(record["reserve_bytes"], 32 * 1024**2, 64 * 1024**3),
            _int(record["timeout_seconds"], 1, 900), output,
            tuple(sorted(parsed)), None if record["workspace_db"] is None else _path(record["workspace_db"]),
            None if provisioning else _wait_digest(record["execution_profile_sha256"]),
        )

    def record(self) -> dict:
        if self.execution_profile_sha256 is None:
            raise DurableSwarmError("unprovisioned GGUF policy")
        return {
            "executable": self.executable, "model": self.model,
            "runtime_sha256": self.runtime_sha256, "model_sha256": self.model_sha256,
            "context_tokens": self.context_tokens, "threads": self.threads,
            "batch_tokens": self.batch_tokens, "kv_bytes_per_token": self.kv_bytes_per_token,
            "reserve_bytes": self.reserve_bytes, "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
            "runtime_libraries": [list(entry) for entry in self.runtime_libraries],
            "workspace_db": self.workspace_db,
            "execution_profile_sha256": self.execution_profile_sha256,
        }

    @property
    def model_id(self) -> str:
        return "dispatch-gguf:" + self.model_sha256[:24]

    @property
    def digest(self) -> str:
        return sha256(_wait_bytes(self.record())).hexdigest()

    def public(self) -> dict:
        return {
            "model_sha256": self.model_sha256, "runtime_sha256": self.runtime_sha256,
            "execution_profile_sha256": self.execution_profile_sha256,
            "policy_sha256": self.digest, "context_tokens": self.context_tokens,
            "max_output_tokens": self.max_output_tokens, "threads": self.threads,
            "timeout_seconds": self.timeout_seconds, "cpu_only": True,
            "shared_workspace_lease": self.workspace_db is not None,
            "runtime_library_pins": len(self.runtime_libraries),
            "system_library_closure_verified": False,
        }

    @classmethod
    def provision(cls, options: dict) -> PinnedGGUFPolicy:
        policy = cls.parse(options, provisioning=True)
        backend = policy.activate()
        return replace(policy, execution_profile_sha256=backend.execution_profile_digest)

    def activate(self):
        from skeleton.ai.runtime.inference.llama_cpp import LlamaCppConfig, LlamaCppModel
        if os.name != "posix":
            raise DurableSwarmError("GGUF dispatcher requires qualified POSIX process custody")
        _trusted_file(self.executable, executable=True)
        _trusted_file(self.model)
        if self.workspace_db is not None:
            _trusted_file(self.workspace_db, private=True)
        for filename, _ in self.runtime_libraries:
            _trusted_file(str(Path(self.executable).parent / filename))
        backend = LlamaCppModel(LlamaCppConfig(
            executable=self.executable, model_path=self.model, model_id=self.model_id,
            timeout_seconds=float(self.timeout_seconds), context_size=self.context_tokens,
            threads=self.threads, batch_size=self.batch_tokens,
            gpu_layers=0, kv_cache_location="host", temperature=0.0,
            max_output_bytes=_MAX_NATIVE_OUTPUT_BYTES, max_stderr_bytes=128 * 1024,
            reject_model_symlink=True, rehash_artifacts_each_run=True,
            kv_bytes_per_token=self.kv_bytes_per_token, runtime_libraries=self.runtime_libraries,
        ))
        if (backend.model_digest != self.model_sha256 or backend.runtime_digest != self.runtime_sha256
                or backend.generation_limits()["context_window"] != self.context_tokens
                or (self.execution_profile_sha256 is not None
                    and backend.execution_profile_digest != self.execution_profile_sha256)):
            raise DurableSwarmError("GGUF activated identity differs from provisioned pins")
        known_kv = backend.serving_metadata.kv_bytes_per_token_upper_bound
        if known_kv is not None and known_kv > self.kv_bytes_per_token:
            raise DurableSwarmError("GGUF KV reservation understates known model geometry")
        return backend

    def request(self, payload: dict):
        from skeleton.ai.runtime.inference.local import LocalInferenceRequest
        if type(payload) is not dict or set(payload) != {"operation", "input"} or payload["operation"] != GGUF_OPERATION:
            raise DurableSwarmError("not an admitted GGUF operation")
        value = payload["input"]
        if (type(value) is not dict or not {"prompt", "max_output_tokens"}.issubset(value)
                or not set(value).issubset({"prompt", "max_output_tokens", "seed"})):
            raise DurableSwarmError("invalid GGUF operation input fields")
        prompt = value["prompt"]
        if (type(prompt) is not str or not prompt.strip() or len(prompt.encode("utf-8")) > 8192
                or "\x00" in prompt):
            raise DurableSwarmError("invalid bounded GGUF prompt")
        output = _int(value["max_output_tokens"], 1, self.max_output_tokens)
        seed = _int(value.get("seed", 0), 0, 0xFFFFFFFE)
        request = LocalInferenceRequest(prompt=prompt, max_output_tokens=output, seed=seed,
                                        temperature=0.0, tool_choice="none")
        if len(request.rendered_input.encode("utf-8")) + 1 + output > self.context_tokens:
            raise DurableSwarmError("GGUF shared context byte bound exceeded")
        return request

    def validate_artifact(self, attempt: HostDispatchAttempt, artifact: bytes) -> bool:
        """Verify request, native frame hash and custody; never certify answer truth."""
        try:
            _check_local_attempt(attempt)
            if type(artifact) is not bytes or not 1 <= len(artifact) <= 65536:
                return False
            payload = attempt.payload()
            request = self.request(payload)
            wrapper = json.loads(artifact)
            if (type(wrapper) is not dict or set(wrapper) != {"version", "payload_sha256", "result"}
                    or type(wrapper["version"]) is not int or wrapper["version"] != 1
                    or wrapper["payload_sha256"] != sha256(attempt.payload_json).hexdigest()
                    or _wait_bytes(wrapper) != artifact):
                return False
            result = wrapper["result"]
            if type(result) is not dict or set(result) != {
                "schema", "policy_sha256", "model_sha256", "runtime_sha256", "model_id",
                "execution_profile_sha256", "native_receipt_sha256", "frame", "text",
                "input_tokens_estimated", "output_tokens_estimated", "finish_reason",
                "usage_source", "quality_certified",
            }:
                return False
            if (result["schema"] != _SCHEMA or result["policy_sha256"] != self.digest
                    or result["model_sha256"] != self.model_sha256
                    or result["runtime_sha256"] != self.runtime_sha256
                    or result["model_id"] != self.model_id
                    or result["execution_profile_sha256"] != self.execution_profile_sha256
                    or result["usage_source"] != "local_model_estimate"
                    or result["quality_certified"] is not False
                    or result["finish_reason"] not in ("completed", "length")):
                return False
            text = result["text"]
            if (type(text) is not str or not text.strip() or text != text.strip()
                    or len(text.encode("utf-8")) > _MAX_NATIVE_OUTPUT_BYTES
                    or type(result["input_tokens_estimated"]) is not int
                    or result["input_tokens_estimated"] != len(request.rendered_input.encode("utf-8")) + 1
                    or type(result["output_tokens_estimated"]) is not int
                    or not 1 <= result["output_tokens_estimated"] <= request.max_output_tokens):
                return False
            frame = result["frame"]
            if (type(frame) is not dict or set(frame) != {
                    "schema", "raw_stdout_digest", "output_framing", "kv_cache_location_requested",
                    "native_kv_observation", "request", "execution_profile", "response_id"}
                    or frame["schema"] != "skeleton.llama-cpp.execution-receipt.v1"
                    or frame["output_framing"] != "raw"
                    or frame["kv_cache_location_requested"] != "host"
                    or frame["request"] != request.digest
                    or frame["execution_profile"] != self.execution_profile_sha256):
                return False
            _wait_digest(frame["raw_stdout_digest"])
            observation = frame["native_kv_observation"]
            if (type(observation) is not dict or len(_wait_bytes(observation)) > 8192
                    or type(observation.get("reported_device_kv_bytes")) is not int
                    or observation["reported_device_kv_bytes"] != 0):
                return False
            response_digest = _native_hash({
                "runtime": self.runtime_sha256, "model": self.model_sha256,
                "request": request.digest, "stdout": frame["raw_stdout_digest"],
                "execution_profile": self.execution_profile_sha256,
            })[:32]
            expected_response = ("local:llama:" + self.runtime_sha256 + ":" + self.model_sha256
                                 + ":" + response_digest)
            if frame["response_id"] != expected_response:
                return False
            expected_receipt = _native_hash({
                **frame, "text": text, "tool_calls": [], "structured_output": None,
                "finish_reason": result["finish_reason"],
                "input_tokens_estimate": result["input_tokens_estimated"],
                "output_tokens_estimate": result["output_tokens_estimated"],
            })
            return _wait_digest(result["native_receipt_sha256"]) == expected_receipt
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, DurableSwarmError):
            return False


class PinnedGGUFTransport(LocalSubprocessTransport):
    """Execute a canonical GGUF turn as an ordinary durable fenced worker job."""

    def __init__(self, custody: SQLiteWorkerCustody, *, policy: PinnedGGUFPolicy,
                 workspace_db: Path, gguf_worker: str, gguf_tenants: frozenset[str],
                 grants: dict[tuple[str, str], frozenset[str]],
                 worker_signers: dict[str, tuple[str, bytes]], timeout_seconds: float) -> None:
        from skeleton.ai.runtime.inference.local import LocalInferenceEngine
        from skeleton.app.jeeves_local_lease import LocalInferenceLease
        super().__init__(custody, grants=grants, worker_signers=worker_signers,
                         timeout_seconds=timeout_seconds)
        if (policy.execution_profile_sha256 is None or gguf_worker not in self._signers
                or type(gguf_tenants) is not frozenset or not gguf_tenants):
            raise DurableSwarmError("GGUF transport requires explicit worker and tenant grants")
        self.policy = policy
        self.gguf_worker = _wait_identifier(gguf_worker)
        self.gguf_tenants = frozenset(_wait_identifier(tenant) for tenant in gguf_tenants)
        self.backend = policy.activate()
        anchor = policy.workspace_db or str(workspace_db)
        _trusted_file(anchor, private=True)
        self._lease = LocalInferenceLease(anchor)
        self.engine = LocalInferenceEngine(self.backend, cache_size=0, max_concurrency=1,
                                           max_queue_size=1, max_batch_size=1)
        # The same canonical backend repeats this resource check immediately
        # before the real process launch. No unqualified GPU allocation.
        self.backend.install_prelaunch_resource_guard(self._check_capacity)

    @property
    def max_execution_seconds(self) -> float:
        return max(super().max_execution_seconds, self.policy.timeout_seconds)

    def _check_capacity(self) -> None:
        from skeleton.ai.runtime.inference.llama_cpp import detect_consumer_hardware_budget
        policy = self.policy
        budget = detect_consumer_hardware_budget(
            kv_bytes_per_token=policy.kv_bytes_per_token,
            target_context_tokens=policy.context_tokens,
        )
        required = (self.backend.model_artifact.size_bytes + self.backend.config.runtime_scratch_bytes
                    + policy.context_tokens * policy.kv_bytes_per_token + policy.reserve_bytes)
        if budget.ram_bytes < required or budget.physical_cpu_cores < policy.threads:
            raise DurableSwarmError("physical host memory or CPU admission refused")

    def __call__(self, attempt: HostDispatchAttempt) -> HostTransportReply:
        _check_local_attempt(attempt)
        payload = attempt.payload()
        if payload.get("operation") != GGUF_OPERATION:
            return super().__call__(attempt)
        if attempt.worker_id != self.gguf_worker or attempt.tenant not in self.gguf_tenants:
            raise DurableSwarmError("GGUF operation outside worker and tenant grant")
        request = self.policy.request(payload)
        # Already committed evidence is replayable without a live model.
        # A start without evidence is not permission to run again.
        new = self.custody.begin(attempt)
        if not new:
            record = self.custody.lookup(attempt.run_id, attempt.lease_token)
            if record is None or record.receipt_sha256 is None:
                raise DurableSwarmError("GGUF attempt has unresolved execution custody")
            bundle = self.custody.resolve(record.receipt_sha256)
            if bundle is None or not self.policy.validate_artifact(attempt, bundle[1]):
                raise DurableSwarmError("GGUF persisted receipt refused")
            return HostTransportReply("success", record.receipt_sha256)
        # Kernel-backed shared workspace exclusion is retained through actual
        # child completion, hash verification and SQLite evidence publication.
        with self._lease.hold():
            self._check_capacity()
            self.backend.assert_identity()
            if self.backend.execution_profile_digest != self.policy.execution_profile_sha256:
                raise DurableSwarmError("GGUF runtime profile changed before dispatch")
            before = self.backend.execution_snapshot()
            deadline = time.monotonic() + self.policy.timeout_seconds
            result = asyncio.run(self.engine.generate(
                request, tenant_scope_id=attempt.tenant, scope_id=attempt.task_id,
                work_class="background", deadline=deadline,
                resource_max_input_tokens=self.policy.context_tokens - request.max_output_tokens,
                resource_max_output_tokens=request.max_output_tokens,
            ))
            after = self.backend.execution_snapshot()
            if (result.cached or result.tool_calls or result.structured_output is not None
                    or result.model_id != self.policy.model_id
                    or result.model_digest != self.policy.model_sha256
                    or result.execution_receipt_digest is None
                    or result.usage_source != "local_model_estimate"
                    or after["processes_started"] != before["processes_started"] + 1
                    or after["processes_exited"] != before["processes_exited"] + 1
                    or any(after[name] for name in ("active_processes", "spawning_processes",
                                                   "draining_processes"))):
                raise DurableSwarmError("GGUF native physical execution receipt incomplete")
            frame = self.backend.execution_receipt_frame(result.execution_receipt_digest)
            data = {"version": 1, "payload_sha256": sha256(attempt.payload_json).hexdigest(),
                    "result": {
                        "schema": _SCHEMA, "policy_sha256": self.policy.digest,
                        "model_sha256": self.policy.model_sha256,
                        "runtime_sha256": self.policy.runtime_sha256, "model_id": self.policy.model_id,
                        "execution_profile_sha256": self.policy.execution_profile_sha256,
                        "native_receipt_sha256": result.execution_receipt_digest,
                        "frame": frame, "text": result.text, "finish_reason": result.finish_reason,
                        "input_tokens_estimated": result.input_tokens,
                        "output_tokens_estimated": result.output_tokens,
                        "usage_source": result.usage_source, "quality_certified": False,
                    }}
            artifact = _wait_bytes(data)
            if not self.policy.validate_artifact(attempt, artifact):
                raise DurableSwarmError("GGUF canonical result hash failed reconstruction")
            issuer, key = self._signers[attempt.worker_id]
            receipt = HostWorkerReceipt.issue(
                run_id=attempt.run_id, issuer=issuer, worker_id=attempt.worker_id,
                task_id=attempt.task_id, lease_token=attempt.lease_token, action="success",
                artifact_sha256=sha256(artifact).hexdigest(), issuer_key=key,
            )
            digest = self.custody.finish(attempt, receipt, artifact)
            return HostTransportReply("success", digest)
