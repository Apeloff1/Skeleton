"""Optional Java retrieval-fusion aggregation accelerator.

Python owns retrieval-plane policy, fragment identity, score contribution
semantics, first-seen ordering, and result construction. This bridge only sends
bounded numeric contribution pairs to a persistent JVM helper for aggregation
and stable top-K selection.
"""
from __future__ import annotations

import atexit
import math
import os
import queue
import shutil
import struct
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_MAGIC = 0x534B5246
_VERSION = 1
_OP_PING = 1
_OP_AGGREGATE_TOP_K = 2
_OP_SHUTDOWN = 3
_STATUS_OK = 0

_MAX_FRAGMENTS = 200_000
_MAX_CONTRIBUTIONS = 2_000_000
_MAX_ERROR_BYTES = 8192

_HEADER_REQUEST = struct.Struct(">IhBq")
_HEADER_RESPONSE = struct.Struct(">IhBBq")
_INT = struct.Struct(">i")
_PING = struct.Struct(">qi")
_AGGREGATE_PREFIX = struct.Struct(">iii")
_CONTRIBUTION = struct.Struct(">id")
_HIT = struct.Struct(">id")


class JvmFusionError(RuntimeError):
    """Base class for optional retrieval fusion accelerator errors."""


class JvmFusionUnavailable(JvmFusionError):
    """Raised when Java or the fusion source launcher cannot start."""


class JvmFusionProtocolError(JvmFusionError):
    """Raised for rejected or malformed accelerator frames."""


class JvmFusionTimeout(JvmFusionError):
    """Raised when the JVM does not answer within the configured deadline."""


@dataclass(frozen=True, slots=True)
class FusionHit:
    index: int
    score: float


@dataclass(frozen=True, slots=True)
class FusionAcceleratorStatus:
    running: bool
    java_binary: str
    source: str
    closed: bool = False
    pid: int | None = None
    server_processors: int | None = None
    starts: int = 0
    start_failures: int = 0
    restarts: int = 0
    requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeouts: int = 0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class JvmFusionConfig:
    java_binary: str
    source: Path
    response_timeout_seconds: float = 10.0
    minimum_contributions: int = 2048
    max_fragments: int = _MAX_FRAGMENTS
    max_contributions: int = _MAX_CONTRIBUTIONS

    def __post_init__(self) -> None:
        if not self.java_binary:
            raise ValueError("java_binary must be non-empty")
        if self.response_timeout_seconds <= 0:
            raise ValueError("response_timeout_seconds must be positive")
        if not 1 <= self.minimum_contributions <= self.max_contributions:
            raise ValueError("minimum_contributions outside supported range")
        if not 1 <= self.max_fragments <= _MAX_FRAGMENTS:
            raise ValueError("max_fragments outside supported range")
        if not 1 <= self.max_contributions <= _MAX_CONTRIBUTIONS:
            raise ValueError("max_contributions outside supported range")

    @classmethod
    def discover(cls) -> "JvmFusionConfig":
        java_binary = os.environ.get("SKELETON_JAVA_BIN") or shutil.which("java") or "java"
        root = Path(__file__).resolve().parents[2]
        source = Path(
            os.environ.get(
                "SKELETON_JVM_RETRIEVAL_SOURCE",
                root / "java-accelerators" / "retrieval" / "FusionMain.java",
            )
        )
        timeout = float(os.environ.get("SKELETON_JVM_RETRIEVAL_TIMEOUT", "10"))
        minimum = int(
            os.environ.get(
                "SKELETON_JVM_RETRIEVAL_MIN_CONTRIBUTIONS",
                "2048",
            )
        )
        return cls(
            java_binary=java_binary,
            source=source,
            response_timeout_seconds=timeout,
            minimum_contributions=minimum,
        )


@dataclass(slots=True)
class _Response:
    op: int
    status: int
    request_id: int
    payload: object


class JvmFusionAccelerator:
    """Persistent stdio client for the bounded Java fusion kernel."""

    def __init__(self, config: JvmFusionConfig | None = None) -> None:
        self.config = config or JvmFusionConfig.discover()
        self._process: subprocess.Popen[bytes] | None = None
        self._responses: queue.Queue[_Response | BaseException] = queue.Queue(
            maxsize=8
        )
        self._request_lock = threading.RLock()
        self._request_id = 0
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._closed = False
        self._last_error: str | None = None
        self._server_processors: int | None = None
        self._starts = 0
        self._start_failures = 0
        self._restarts = 0
        self._requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._timeouts = 0

    @property
    def minimum_contributions(self) -> int:
        return self.config.minimum_contributions

    def __enter__(self) -> "JvmFusionAccelerator":
        self.ping()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> FusionAcceleratorStatus:
        process = self._process
        running = process is not None and process.poll() is None
        return FusionAcceleratorStatus(
            running=running,
            java_binary=self.config.java_binary,
            source=str(self.config.source),
            closed=self._closed,
            pid=process.pid if running and process is not None else None,
            server_processors=self._server_processors,
            starts=self._starts,
            start_failures=self._start_failures,
            restarts=self._restarts,
            requests=self._requests,
            successful_requests=self._successful_requests,
            failed_requests=self._failed_requests,
            timeouts=self._timeouts,
            last_error=self._last_error,
        )

    def ping(self) -> int:
        response = self._request(_OP_PING, b"")
        if not isinstance(response.payload, tuple):
            raise JvmFusionProtocolError("ping response type mismatch")
        _server_nanos, processors = response.payload
        self._server_processors = int(processors)
        return int(processors)

    def aggregate_top_k(
        self,
        fragment_count: int,
        contributions: Sequence[tuple[int, float]],
        top_k: int,
    ) -> list[FusionHit]:
        if (
            isinstance(fragment_count, bool)
            or not isinstance(fragment_count, int)
            or not 1 <= fragment_count <= self.config.max_fragments
        ):
            raise ValueError("fragment_count outside supported range")
        contribution_count = len(contributions)
        if not 1 <= contribution_count <= self.config.max_contributions:
            raise ValueError("contribution count outside supported range")
        if (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or not 1 <= top_k <= fragment_count
        ):
            raise ValueError("top_k outside fragment range")

        payload = bytearray(
            _AGGREGATE_PREFIX.pack(
                fragment_count,
                contribution_count,
                top_k,
            )
        )
        for index, value in contributions:
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < fragment_count
            ):
                raise ValueError("fragment index outside supported range")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError("contribution must be finite")
            payload.extend(_CONTRIBUTION.pack(index, numeric))

        response = self._request(_OP_AGGREGATE_TOP_K, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmFusionProtocolError("aggregate response type mismatch")
        hits = response.payload
        self._validate_hits(
            hits,
            fragment_count=fragment_count,
            top_k=top_k,
        )
        return hits

    def close(self) -> None:
        with self._request_lock:
            if self._closed:
                return
            self._closed = True
            process = self._process
            if process is not None and process.poll() is None:
                try:
                    request_id = self._next_request_id()
                    assert process.stdin is not None
                    process.stdin.write(
                        _HEADER_REQUEST.pack(
                            _MAGIC,
                            _VERSION,
                            _OP_SHUTDOWN,
                            request_id,
                        )
                    )
                    process.stdin.flush()
                    try:
                        self._responses.get(
                            timeout=min(
                                1.0,
                                self.config.response_timeout_seconds,
                            )
                        )
                    except queue.Empty:
                        pass
                except Exception:
                    pass
            self._terminate_process()

    def restart(self) -> None:
        with self._request_lock:
            self._restarts += 1
            self._terminate_process()
            self._closed = False
            self._last_error = None
            self._drain_response_queue()
        self.ping()

    def _request(self, op: int, payload: bytes) -> _Response:
        with self._request_lock:
            if self._closed:
                raise JvmFusionUnavailable("retrieval fusion accelerator is closed")
            self._ensure_started()
            process = self._process
            assert process is not None and process.stdin is not None
            request_id = self._next_request_id()
            self._requests += 1

            try:
                process.stdin.write(
                    _HEADER_REQUEST.pack(
                        _MAGIC,
                        _VERSION,
                        op,
                        request_id,
                    )
                )
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._failed_requests += 1
                self._last_error = (
                    "retrieval fusion accelerator write failed: "
                    f"{type(exc).__name__}"
                )
                self._terminate_process()
                raise JvmFusionUnavailable(
                    self._diagnostic(self._last_error)
                ) from exc

            try:
                item = self._responses.get(
                    timeout=self.config.response_timeout_seconds
                )
            except queue.Empty as exc:
                self._failed_requests += 1
                self._timeouts += 1
                self._last_error = "retrieval fusion accelerator response timed out"
                self._terminate_process()
                raise JvmFusionTimeout(
                    self._diagnostic(self._last_error)
                ) from exc

            if isinstance(item, BaseException):
                self._failed_requests += 1
                self._last_error = str(item)
                self._terminate_process()
                raise JvmFusionUnavailable(
                    self._diagnostic(str(item))
                ) from item
            if item.request_id != request_id or item.op != op:
                self._failed_requests += 1
                self._last_error = "retrieval fusion response correlation mismatch"
                self._terminate_process()
                raise JvmFusionProtocolError(self._last_error)
            if item.status != _STATUS_OK:
                self._failed_requests += 1
                self._last_error = str(item.payload)
                raise JvmFusionProtocolError(str(item.payload))

            self._successful_requests += 1
            return item

    def _ensure_started(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            return
        self._start_process()

    def _start_process(self) -> None:
        if not self.config.source.is_file():
            message = (
                "retrieval fusion accelerator source not found: "
                f"{self.config.source}"
            )
            self._start_failures += 1
            self._last_error = message
            raise JvmFusionUnavailable(message)

        java = (
            shutil.which(self.config.java_binary)
            if os.path.sep not in self.config.java_binary
            else self.config.java_binary
        )
        if not java or not Path(java).exists():
            message = f"java binary not found: {self.config.java_binary}"
            self._start_failures += 1
            self._last_error = message
            raise JvmFusionUnavailable(message)

        self._drain_response_queue()
        self._stderr_tail.clear()
        try:
            process = subprocess.Popen(
                [java, str(self.config.source), "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                bufsize=0,
            )
        except OSError as exc:
            message = f"failed to start Java: {exc}"
            self._start_failures += 1
            self._last_error = message
            raise JvmFusionUnavailable(message) from exc

        self._process = process
        self._starts += 1
        self._reader = threading.Thread(
            target=self._reader_loop,
            args=(process,),
            name="skeleton-jvm-retrieval-reader",
            daemon=True,
        )
        self._stderr_reader = threading.Thread(
            target=self._stderr_loop,
            args=(process,),
            name="skeleton-jvm-retrieval-stderr",
            daemon=True,
        )
        self._reader.start()
        self._stderr_reader.start()

    def _reader_loop(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        try:
            while True:
                header = self._read_exact(
                    process.stdout,
                    _HEADER_RESPONSE.size,
                )
                magic, version, op, status, request_id = (
                    _HEADER_RESPONSE.unpack(header)
                )
                if magic != _MAGIC or version != _VERSION:
                    raise JvmFusionProtocolError(
                        "invalid retrieval fusion response header"
                    )

                if status != _STATUS_OK:
                    length = _INT.unpack(
                        self._read_exact(process.stdout, _INT.size)
                    )[0]
                    if not 0 <= length <= _MAX_ERROR_BYTES:
                        raise JvmFusionProtocolError(
                            "invalid error payload length"
                        )
                    message = self._read_exact(
                        process.stdout,
                        length,
                    ).decode("utf-8", "replace")
                    self._responses.put(
                        _Response(
                            op,
                            status,
                            request_id,
                            message,
                        )
                    )
                    continue

                payload = self._read_success_payload(
                    process.stdout,
                    op,
                )
                self._responses.put(
                    _Response(
                        op,
                        status,
                        request_id,
                        payload,
                    )
                )
        except EOFError:
            if not self._closed:
                return_code = process.poll()
                detail = (
                    "retrieval fusion accelerator stdout closed"
                    if return_code is None
                    else (
                        "retrieval fusion accelerator exited with code "
                        f"{return_code}"
                    )
                )
                self._responses.put(JvmFusionUnavailable(detail))
        except BaseException as exc:
            if not self._closed:
                self._responses.put(exc)

    def _stderr_loop(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stderr is not None
        try:
            while True:
                raw = process.stderr.readline()
                if not raw:
                    return
                line = raw.decode("utf-8", "replace").strip()
                if line:
                    self._stderr_tail.append(line[:1000])
        except Exception:
            return

    def _read_success_payload(self, stream: object, op: int) -> object:
        if op == _OP_PING:
            return _PING.unpack(
                self._read_exact(
                    stream,
                    _PING.size,
                )
            )
        if op == _OP_AGGREGATE_TOP_K:
            count = _INT.unpack(
                self._read_exact(
                    stream,
                    _INT.size,
                )
            )[0]
            if not 0 <= count <= self.config.max_fragments:
                raise JvmFusionProtocolError("invalid fusion hit count")
            hits: list[FusionHit] = []
            for _ in range(count):
                index, score = _HIT.unpack(
                    self._read_exact(
                        stream,
                        _HIT.size,
                    )
                )
                hits.append(FusionHit(index=index, score=score))
            return hits
        if op == _OP_SHUTDOWN:
            return None
        raise JvmFusionProtocolError(
            f"unknown response operation: {op}"
        )

    @staticmethod
    def _read_exact(stream: object, size: int) -> bytes:
        read = getattr(stream, "read")
        chunks = bytearray()
        while len(chunks) < size:
            part = read(size - len(chunks))
            if not part:
                raise EOFError(
                    "unexpected EOF from retrieval fusion accelerator"
                )
            chunks.extend(part)
        return bytes(chunks)

    @staticmethod
    def _validate_hits(
        hits: object,
        *,
        fragment_count: int,
        top_k: int,
    ) -> None:
        if not isinstance(hits, list):
            raise JvmFusionProtocolError("invalid fusion top-k response")
        if len(hits) != min(top_k, fragment_count):
            raise JvmFusionProtocolError("invalid fusion top-k hit count")

        previous: FusionHit | None = None
        seen: set[int] = set()
        for hit in hits:
            if not isinstance(hit, FusionHit):
                raise JvmFusionProtocolError("invalid fusion hit")
            if not 0 <= hit.index < fragment_count:
                raise JvmFusionProtocolError(
                    "fusion hit index outside fragment range"
                )
            if hit.index in seen:
                raise JvmFusionProtocolError(
                    "duplicate fusion hit index"
                )
            if not math.isfinite(hit.score):
                raise JvmFusionProtocolError(
                    "non-finite fusion score"
                )
            if previous is not None and (
                hit.score > previous.score
                or (
                    hit.score == previous.score
                    and hit.index < previous.index
                )
            ):
                raise JvmFusionProtocolError(
                    "fusion response is not stably ordered"
                )
            seen.add(hit.index)
            previous = hit

    def _next_request_id(self) -> int:
        self._request_id = (
            self._request_id % 0x7FFF_FFFF_FFFF_FFFE
        ) + 1
        return self._request_id

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        for stream in (
            process.stdin,
            process.stdout,
            process.stderr,
        ):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass

    def _drain_response_queue(self) -> None:
        while True:
            try:
                self._responses.get_nowait()
            except queue.Empty:
                return

    def _diagnostic(self, message: str) -> str:
        if not self._stderr_tail:
            return message
        return (
            f"{message}; java stderr: "
            f"{' | '.join(self._stderr_tail)}"
        )


_default_lock = threading.Lock()
_default_accelerator: JvmFusionAccelerator | None = None


def get_default_fusion_accelerator() -> JvmFusionAccelerator:
    global _default_accelerator
    with _default_lock:
        if _default_accelerator is None:
            _default_accelerator = JvmFusionAccelerator()
        return _default_accelerator


def close_default_fusion_accelerator() -> None:
    global _default_accelerator
    with _default_lock:
        accelerator = _default_accelerator
        _default_accelerator = None
    if accelerator is not None:
        accelerator.close()


atexit.register(close_default_fusion_accelerator)


__all__ = [
    "FusionAcceleratorStatus",
    "FusionHit",
    "JvmFusionAccelerator",
    "JvmFusionConfig",
    "JvmFusionError",
    "JvmFusionProtocolError",
    "JvmFusionTimeout",
    "JvmFusionUnavailable",
    "close_default_fusion_accelerator",
    "get_default_fusion_accelerator",
]
