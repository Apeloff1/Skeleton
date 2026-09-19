"""Optional Java 21 accelerator for high-volume observability batches.

Python remains authoritative for MetricsCollector and AnomalyDetector state. This
module only offloads large numeric batches when explicitly requested. It uses a
small bounded binary protocol over a private subprocess stdio channel; no socket,
server, or Java dependency is introduced into the normal Skeleton startup path.
"""
from __future__ import annotations

import array
import atexit
import math
import os
import queue
import shutil
import struct
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

_MAGIC = 0x534B4F42
_VERSION = 1
_OP_PING = 1
_OP_SUMMARY = 2
_OP_MANY_SUMMARIES = 3
_OP_ANOMALY_SCAN = 4
_OP_SHUTDOWN = 5
_STATUS_OK = 0
_MAX_VALUES = 2_000_000
_MAX_SERIES = 4096
_HEADER_REQUEST = struct.Struct(">IhBq")
_HEADER_RESPONSE = struct.Struct(">IhBBq")
_INT = struct.Struct(">i")
_PING = struct.Struct(">qi")
_SUMMARY = struct.Struct(">q10d")
_ANOMALY = struct.Struct(">??dd")


class JvmAcceleratorError(RuntimeError):
    """Base class for optional accelerator failures."""


class JvmAcceleratorUnavailable(JvmAcceleratorError):
    """Raised when Java or the accelerator source cannot be started."""


class JvmAcceleratorProtocolError(JvmAcceleratorError):
    """Raised when the JVM returns a malformed or rejected frame."""


class JvmAcceleratorTimeout(JvmAcceleratorError):
    """Raised when the accelerator misses the response deadline."""


@dataclass(frozen=True, slots=True)
class HistogramSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    sample_variance: float
    sample_stdev: float
    p50: float
    p90: float
    p95: float
    p99: float
    total: float

    def metrics_fields(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "min": self.minimum,
            "max": self.maximum,
            "mean": self.mean,
            "p50": self.p50,
            "p99": self.p99,
        }


@dataclass(frozen=True, slots=True)
class AnomalyScanRow:
    ready: bool
    anomalous: bool
    mean: float
    stdev: float


@dataclass(frozen=True, slots=True)
class AcceleratorStatus:
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
class JvmAcceleratorConfig:
    java_binary: str
    source: Path
    response_timeout_seconds: float = 10.0
    max_values: int = _MAX_VALUES
    max_series: int = _MAX_SERIES
    minimum_batch_values: int = 2048

    def __post_init__(self) -> None:
        if not self.java_binary:
            raise ValueError("java_binary must be non-empty")
        if self.response_timeout_seconds <= 0:
            raise ValueError("response_timeout_seconds must be positive")
        if not 1 <= self.max_values <= _MAX_VALUES:
            raise ValueError("max_values outside supported range")
        if not 1 <= self.max_series <= _MAX_SERIES:
            raise ValueError("max_series outside supported range")
        if self.minimum_batch_values < 1:
            raise ValueError("minimum_batch_values must be positive")

    @classmethod
    def discover(cls) -> "JvmAcceleratorConfig":
        java_binary = os.environ.get("SKELETON_JAVA_BIN") or shutil.which("java") or "java"
        root = Path(__file__).resolve().parents[2]
        source = Path(
            os.environ.get(
                "SKELETON_JVM_OBSERVABILITY_SOURCE",
                root / "java-accelerators" / "observability" / "AcceleratorMain.java",
            )
        )
        timeout = float(os.environ.get("SKELETON_JVM_OBSERVABILITY_TIMEOUT", "10"))
        minimum = int(os.environ.get("SKELETON_JVM_OBSERVABILITY_MIN_BATCH", "2048"))
        return cls(
            java_binary=java_binary,
            source=source,
            response_timeout_seconds=timeout,
            minimum_batch_values=minimum,
        )


@dataclass(slots=True)
class _Response:
    op: int
    status: int
    request_id: int
    payload: object


class JvmObservabilityAccelerator:
    """Lazy, restartable Java source-launcher client."""

    def __init__(self, config: JvmAcceleratorConfig | None = None) -> None:
        self.config = config or JvmAcceleratorConfig.discover()
        self._process: subprocess.Popen[bytes] | None = None
        self._responses: queue.Queue[_Response | BaseException] = queue.Queue(maxsize=8)
        self._request_lock = threading.RLock()
        self._request_id = 0
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._last_error: str | None = None
        self._server_processors: int | None = None
        self._closed = False
        self._starts = 0
        self._start_failures = 0
        self._restarts = 0
        self._requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._timeouts = 0

    @property
    def minimum_batch_values(self) -> int:
        return self.config.minimum_batch_values

    def __enter__(self) -> "JvmObservabilityAccelerator":
        self.ping()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> AcceleratorStatus:
        process = self._process
        running = process is not None and process.poll() is None
        return AcceleratorStatus(
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
            raise JvmAcceleratorProtocolError("ping response type mismatch")
        _server_nanos, processors = response.payload
        self._server_processors = int(processors)
        return int(processors)

    def summarize(self, values: Sequence[float] | Iterable[float]) -> HistogramSummary:
        normalized = self._normalize_values(values, allow_empty=False)
        response = self._request(_OP_SUMMARY, self._encode_values(normalized))
        if not isinstance(response.payload, HistogramSummary):
            raise JvmAcceleratorProtocolError("summary response type mismatch")
        return response.payload

    def summarize_many(
        self,
        series: Sequence[Sequence[float] | Iterable[float]],
    ) -> list[HistogramSummary]:
        if not series:
            return []
        if len(series) > self.config.max_series:
            raise ValueError("series count exceeds accelerator bound")

        payload = bytearray(_INT.pack(len(series)))
        total = 0
        for values in series:
            normalized = self._normalize_values(values, allow_empty=False)
            total += len(normalized)
            if total > self.config.max_values:
                raise ValueError("aggregate value count exceeds accelerator bound")
            payload.extend(self._encode_values(normalized))

        response = self._request(_OP_MANY_SUMMARIES, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmAcceleratorProtocolError("summary batch response type mismatch")
        summaries = response.payload
        if len(summaries) != len(series) or not all(
            isinstance(item, HistogramSummary) for item in summaries
        ):
            raise JvmAcceleratorProtocolError("summary count mismatch")
        return summaries

    def scan_anomalies(
        self,
        history: Sequence[float] | Iterable[float],
        incoming: Sequence[float] | Iterable[float],
        *,
        window_size: int,
        threshold: float = 3.0,
        include_current: bool = False,
    ) -> list[AnomalyScanRow]:
        if not 10 <= window_size <= self.config.max_values:
            raise ValueError("window_size outside supported range")
        if not math.isfinite(threshold) or not 0.0 < threshold <= 1000.0:
            raise ValueError("threshold must be finite and positive")

        old = self._normalize_values(history, allow_empty=True, max_count=window_size)
        new = self._normalize_values(incoming, allow_empty=True)
        if not new:
            return []

        payload = bytearray()
        payload.extend(_INT.pack(window_size))
        payload.extend(struct.pack(">d", threshold))
        payload.extend(struct.pack(">?", bool(include_current)))
        payload.extend(self._encode_values(old))
        payload.extend(self._encode_values(new))
        response = self._request(_OP_ANOMALY_SCAN, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmAcceleratorProtocolError("anomaly response type mismatch")
        rows = response.payload
        if len(rows) != len(new) or not all(isinstance(item, AnomalyScanRow) for item in rows):
            raise JvmAcceleratorProtocolError("anomaly row count mismatch")
        return rows

    def close(self) -> None:
        with self._request_lock:
            if self._closed:
                return
            self._closed = True
            process = self._process
            if process is not None and process.poll() is None:
                try:
                    request_id = self._next_request_id()
                    frame = _HEADER_REQUEST.pack(_MAGIC, _VERSION, _OP_SHUTDOWN, request_id)
                    assert process.stdin is not None
                    process.stdin.write(frame)
                    process.stdin.flush()
                    try:
                        self._responses.get(timeout=min(1.0, self.config.response_timeout_seconds))
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
                raise JvmAcceleratorUnavailable("accelerator is closed")
            self._ensure_started()
            process = self._process
            assert process is not None and process.stdin is not None
            request_id = self._next_request_id()
            self._requests += 1
            frame = _HEADER_REQUEST.pack(_MAGIC, _VERSION, op, request_id) + payload
            try:
                process.stdin.write(frame)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._failed_requests += 1
                self._last_error = f"accelerator write failed: {type(exc).__name__}"
                self._terminate_process()
                raise JvmAcceleratorUnavailable(self._diagnostic(self._last_error)) from exc

            try:
                item = self._responses.get(timeout=self.config.response_timeout_seconds)
            except queue.Empty as exc:
                self._failed_requests += 1
                self._timeouts += 1
                self._last_error = "accelerator response timed out"
                self._terminate_process()
                raise JvmAcceleratorTimeout(self._diagnostic(self._last_error)) from exc

            if isinstance(item, BaseException):
                self._failed_requests += 1
                self._last_error = str(item)
                self._terminate_process()
                raise JvmAcceleratorUnavailable(self._diagnostic(str(item))) from item
            if item.request_id != request_id or item.op != op:
                self._failed_requests += 1
                self._last_error = "accelerator response correlation mismatch"
                self._terminate_process()
                raise JvmAcceleratorProtocolError(self._last_error)
            if item.status != _STATUS_OK:
                self._failed_requests += 1
                message = str(item.payload)
                self._last_error = message
                raise JvmAcceleratorProtocolError(message)
            self._successful_requests += 1
            return item

    def _ensure_started(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            return
        self._start_process()

    def _start_process(self) -> None:
        if not self.config.source.is_file():
            message = f"accelerator source not found: {self.config.source}"
            self._start_failures += 1
            self._last_error = message
            raise JvmAcceleratorUnavailable(message)
        java = (
            shutil.which(self.config.java_binary)
            if os.path.sep not in self.config.java_binary
            else self.config.java_binary
        )
        if not java or not Path(java).exists():
            message = f"java binary not found: {self.config.java_binary}"
            self._start_failures += 1
            self._last_error = message
            raise JvmAcceleratorUnavailable(message)

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
            raise JvmAcceleratorUnavailable(message) from exc

        self._process = process
        self._starts += 1
        self._reader = threading.Thread(
            target=self._reader_loop,
            args=(process,),
            name="skeleton-jvm-observability-reader",
            daemon=True,
        )
        self._stderr_reader = threading.Thread(
            target=self._stderr_loop,
            args=(process,),
            name="skeleton-jvm-observability-stderr",
            daemon=True,
        )
        self._reader.start()
        self._stderr_reader.start()

    def _reader_loop(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        try:
            while True:
                header = self._read_exact(process.stdout, _HEADER_RESPONSE.size)
                magic, version, op, status, request_id = _HEADER_RESPONSE.unpack(header)
                if magic != _MAGIC or version != _VERSION:
                    raise JvmAcceleratorProtocolError("invalid response header")
                if status != _STATUS_OK:
                    length = _INT.unpack(self._read_exact(process.stdout, _INT.size))[0]
                    if not 0 <= length <= 8192:
                        raise JvmAcceleratorProtocolError("invalid error payload length")
                    message = self._read_exact(process.stdout, length).decode("utf-8", "replace")
                    self._responses.put(_Response(op, status, request_id, message))
                    continue

                payload = self._read_success_payload(process.stdout, op)
                self._responses.put(_Response(op, status, request_id, payload))
        except EOFError:
            if not self._closed:
                return_code = process.poll()
                detail = (
                    "accelerator stdout closed"
                    if return_code is None
                    else f"accelerator exited with code {return_code}"
                )
                self._responses.put(JvmAcceleratorUnavailable(detail))
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
            return _PING.unpack(self._read_exact(stream, _PING.size))
        if op == _OP_SUMMARY:
            return self._decode_summary(self._read_exact(stream, _SUMMARY.size))
        if op == _OP_MANY_SUMMARIES:
            count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
            if not 0 <= count <= self.config.max_series:
                raise JvmAcceleratorProtocolError("invalid summary count")
            return [
                self._decode_summary(self._read_exact(stream, _SUMMARY.size))
                for _ in range(count)
            ]
        if op == _OP_ANOMALY_SCAN:
            count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
            if not 0 <= count <= self.config.max_values:
                raise JvmAcceleratorProtocolError("invalid anomaly row count")
            rows: list[AnomalyScanRow] = []
            for _ in range(count):
                ready, anomalous, mean, stdev = _ANOMALY.unpack(
                    self._read_exact(stream, _ANOMALY.size)
                )
                rows.append(AnomalyScanRow(ready, anomalous, mean, stdev))
            return rows
        if op == _OP_SHUTDOWN:
            return None
        raise JvmAcceleratorProtocolError(f"unknown response operation: {op}")

    @staticmethod
    def _read_exact(stream: object, size: int) -> bytes:
        read = getattr(stream, "read")
        chunks = bytearray()
        while len(chunks) < size:
            part = read(size - len(chunks))
            if not part:
                raise EOFError("unexpected EOF from accelerator")
            chunks.extend(part)
        return bytes(chunks)

    @staticmethod
    def _decode_summary(payload: bytes) -> HistogramSummary:
        (
            count,
            minimum,
            maximum,
            mean,
            variance,
            stdev,
            p50,
            p90,
            p95,
            p99,
            total,
        ) = _SUMMARY.unpack(payload)
        return HistogramSummary(
            count=count,
            minimum=minimum,
            maximum=maximum,
            mean=mean,
            sample_variance=variance,
            sample_stdev=stdev,
            p50=p50,
            p90=p90,
            p95=p95,
            p99=p99,
            total=total,
        )

    def _normalize_values(
        self,
        values: Sequence[float] | Iterable[float],
        *,
        allow_empty: bool,
        max_count: int | None = None,
    ) -> list[float]:
        normalized = [float(value) for value in values]
        limit = self.config.max_values if max_count is None else min(max_count, self.config.max_values)
        if len(normalized) > limit:
            raise ValueError("value count exceeds accelerator bound")
        if not allow_empty and not normalized:
            raise ValueError("at least one value is required")
        if any(not math.isfinite(value) for value in normalized):
            raise ValueError("accelerator accepts finite values only")
        return normalized

    @staticmethod
    def _encode_values(values: Sequence[float]) -> bytes:
        payload = bytearray(_INT.pack(len(values)))
        if not values:
            return bytes(payload)
        doubles = array.array("d", values)
        if sys.byteorder == "little":
            doubles.byteswap()
        payload.extend(doubles.tobytes())
        return bytes(payload)

    def _next_request_id(self) -> int:
        self._request_id = (self._request_id % 0x7FFF_FFFF_FFFF_FFFE) + 1
        return self._request_id

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
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
        tail = " | ".join(self._stderr_tail)
        return f"{message}; java stderr: {tail}"


_default_lock = threading.Lock()
_default_accelerator: JvmObservabilityAccelerator | None = None


def get_default_accelerator() -> JvmObservabilityAccelerator:
    global _default_accelerator
    with _default_lock:
        if _default_accelerator is None:
            _default_accelerator = JvmObservabilityAccelerator()
        return _default_accelerator


def close_default_accelerator() -> None:
    global _default_accelerator
    with _default_lock:
        accelerator = _default_accelerator
        _default_accelerator = None
    if accelerator is not None:
        accelerator.close()


atexit.register(close_default_accelerator)
