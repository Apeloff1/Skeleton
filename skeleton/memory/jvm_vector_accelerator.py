"""Optional Java dense-vector top-K accelerator.

The Python VectorStore keeps ownership of embeddings, metadata filters, document
objects, and score normalization. This helper only moves a large cosine scoring
batch into a persistent JVM process when the caller explicitly enables it.
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
from typing import Sequence

_MAGIC = 0x534B5653
_VERSION = 1
_OP_PING = 1
_OP_TOP_K = 2
_OP_SHUTDOWN = 3
_OP_BATCH_TOP_K = 4
_OP_RANGE = 5
_OP_BATCH_RANGE = 6
_STATUS_OK = 0
_MAX_DIMENSIONS = 4096
_MAX_CANDIDATES = 100_000
_MAX_QUERIES = 512
_MAX_RANGE_HITS = 1_000_000
_MAX_ELEMENTS = 4_000_000
_HEADER_REQUEST = struct.Struct(">IhBq")
_HEADER_RESPONSE = struct.Struct(">IhBBq")
_INT = struct.Struct(">i")
_PING = struct.Struct(">qi")
_TOP_K_PREFIX = struct.Struct(">iiid")
_BATCH_TOP_K_PREFIX = struct.Struct(">iiii")
_RANGE_PREFIX = struct.Struct(">iiidd")
_BATCH_RANGE_PREFIX = struct.Struct(">iiiid")
_HIT = struct.Struct(">id")


class JvmVectorError(RuntimeError):
    """Base class for optional dense-vector accelerator errors."""


class JvmVectorUnavailable(JvmVectorError):
    """Raised when Java or the vector source launcher cannot start."""


class JvmVectorProtocolError(JvmVectorError):
    """Raised for rejected or malformed accelerator frames."""


class JvmVectorTimeout(JvmVectorError):
    """Raised when the JVM does not answer within the configured deadline."""


@dataclass(frozen=True, slots=True)
class VectorHit:
    index: int
    similarity: float


@dataclass(frozen=True, slots=True)
class VectorAcceleratorStatus:
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
class JvmVectorConfig:
    java_binary: str
    source: Path
    response_timeout_seconds: float = 15.0
    minimum_candidates: int = 512
    max_dimensions: int = _MAX_DIMENSIONS
    max_candidates: int = _MAX_CANDIDATES
    max_elements: int = _MAX_ELEMENTS

    def __post_init__(self) -> None:
        if not self.java_binary:
            raise ValueError("java_binary must be non-empty")
        if self.response_timeout_seconds <= 0:
            raise ValueError("response_timeout_seconds must be positive")
        if not 1 <= self.minimum_candidates <= self.max_candidates:
            raise ValueError("minimum_candidates outside supported range")
        if not 1 <= self.max_dimensions <= _MAX_DIMENSIONS:
            raise ValueError("max_dimensions outside supported range")
        if not 1 <= self.max_candidates <= _MAX_CANDIDATES:
            raise ValueError("max_candidates outside supported range")
        if not 1 <= self.max_elements <= _MAX_ELEMENTS:
            raise ValueError("max_elements outside supported range")

    @classmethod
    def discover(cls) -> "JvmVectorConfig":
        java_binary = os.environ.get("SKELETON_JAVA_BIN") or shutil.which("java") or "java"
        root = Path(__file__).resolve().parents[2]
        source = Path(
            os.environ.get(
                "SKELETON_JVM_VECTOR_SOURCE",
                root / "java-accelerators" / "vector" / "VectorSearchMain.java",
            )
        )
        timeout = float(os.environ.get("SKELETON_JVM_VECTOR_TIMEOUT", "15"))
        minimum = int(os.environ.get("SKELETON_JVM_VECTOR_MIN_CANDIDATES", "512"))
        return cls(
            java_binary=java_binary,
            source=source,
            response_timeout_seconds=timeout,
            minimum_candidates=minimum,
        )


@dataclass(slots=True)
class _Response:
    op: int
    status: int
    request_id: int
    payload: object


class JvmVectorAccelerator:
    """Persistent stdio client for the bounded Java vector kernel."""

    def __init__(self, config: JvmVectorConfig | None = None) -> None:
        self.config = config or JvmVectorConfig.discover()
        self._process: subprocess.Popen[bytes] | None = None
        self._responses: queue.Queue[_Response | BaseException] = queue.Queue(maxsize=8)
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
    def minimum_candidates(self) -> int:
        return self.config.minimum_candidates

    def __enter__(self) -> "JvmVectorAccelerator":
        self.ping()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> VectorAcceleratorStatus:
        process = self._process
        running = process is not None and process.poll() is None
        return VectorAcceleratorStatus(
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
            raise JvmVectorProtocolError("ping response type mismatch")
        _server_nanos, processors = response.payload
        self._server_processors = int(processors)
        return int(processors)

    def top_k(
        self,
        query: Sequence[float],
        query_norm: float,
        candidates: Sequence[tuple[Sequence[float], float]],
        top_k: int,
    ) -> list[VectorHit]:
        dimensions = len(query)
        candidate_count = len(candidates)

        if not 1 <= dimensions <= self.config.max_dimensions:
            raise ValueError("query dimensions outside supported range")
        if not 1 <= candidate_count <= self.config.max_candidates:
            raise ValueError("candidate count outside supported range")
        if dimensions * candidate_count > self.config.max_elements:
            raise ValueError("vector element count exceeds accelerator bound")
        if not 1 <= top_k <= candidate_count:
            raise ValueError("top_k outside candidate range")
        if not math.isfinite(query_norm) or query_norm <= 0:
            raise ValueError("query_norm must be finite and positive")

        payload = bytearray(
            _TOP_K_PREFIX.pack(dimensions, candidate_count, top_k, float(query_norm))
        )
        payload.extend(self._encode_vector(query, dimensions))

        for vector, norm in candidates:
            if len(vector) != dimensions:
                raise ValueError("candidate dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("candidate norm must be finite and positive")
            payload.extend(struct.pack(">d", norm_value))
            payload.extend(self._encode_vector(vector, dimensions))

        response = self._request(_OP_TOP_K, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmVectorProtocolError("top-k response type mismatch")
        hits = response.payload
        self._validate_hits(hits, candidate_count, top_k)
        return hits

    def top_k_many(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        candidates: Sequence[tuple[Sequence[float], float]],
        top_k: int,
    ) -> list[list[VectorHit]]:
        """Score many queries against one shared candidate matrix.

        The candidate matrix is serialized once, which is the main reason this
        operation can beat repeated single-query IPC for bulk retrieval.
        """
        query_count = len(queries)
        candidate_count = len(candidates)
        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside supported range")
        if not 1 <= candidate_count <= self.config.max_candidates:
            raise ValueError("candidate count outside supported range")

        dimensions = len(queries[0][0])
        if not 1 <= dimensions <= self.config.max_dimensions:
            raise ValueError("query dimensions outside supported range")
        if dimensions * (query_count + candidate_count) > self.config.max_elements:
            raise ValueError("vector element count exceeds accelerator bound")
        if not 1 <= top_k <= candidate_count:
            raise ValueError("top_k outside candidate range")

        payload = bytearray(
            _BATCH_TOP_K_PREFIX.pack(
                dimensions,
                query_count,
                candidate_count,
                top_k,
            )
        )
        for query, norm in queries:
            if len(query) != dimensions:
                raise ValueError("query dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("query_norm must be finite and positive")
            payload.extend(struct.pack(">d", norm_value))
            payload.extend(self._encode_vector(query, dimensions))

        for vector, norm in candidates:
            if len(vector) != dimensions:
                raise ValueError("candidate dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("candidate norm must be finite and positive")
            payload.extend(struct.pack(">d", norm_value))
            payload.extend(self._encode_vector(vector, dimensions))

        response = self._request(_OP_BATCH_TOP_K, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmVectorProtocolError("batch top-k response type mismatch")
        batches = response.payload
        if len(batches) != query_count:
            raise JvmVectorProtocolError("batch top-k query count mismatch")
        for hits in batches:
            self._validate_hits(hits, candidate_count, top_k)
        return batches

    def range_search(
        self,
        query: Sequence[float],
        query_norm: float,
        candidates: Sequence[tuple[Sequence[float], float]],
        similarity_threshold: float,
        *,
        max_hits: int = _MAX_RANGE_HITS,
    ) -> list[VectorHit]:
        """Return all candidates at or above a cosine similarity threshold."""
        dimensions = len(query)
        candidate_count = len(candidates)
        threshold = float(similarity_threshold)

        if not 1 <= dimensions <= self.config.max_dimensions:
            raise ValueError("query dimensions outside supported range")
        if not 1 <= candidate_count <= self.config.max_candidates:
            raise ValueError("candidate count outside supported range")
        if dimensions * candidate_count > self.config.max_elements:
            raise ValueError("vector element count exceeds accelerator bound")
        if not 1 <= max_hits <= min(candidate_count, _MAX_RANGE_HITS):
            raise ValueError("max_hits outside candidate range")
        if not math.isfinite(threshold) or not -1.0 <= threshold <= 1.0:
            raise ValueError("similarity_threshold outside [-1, 1]")
        if not math.isfinite(query_norm) or query_norm <= 0:
            raise ValueError("query_norm must be finite and positive")

        payload = bytearray(
            _RANGE_PREFIX.pack(
                dimensions,
                candidate_count,
                max_hits,
                threshold,
                float(query_norm),
            )
        )
        payload.extend(self._encode_vector(query, dimensions))
        for vector, norm in candidates:
            if len(vector) != dimensions:
                raise ValueError("candidate dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("candidate norm must be finite and positive")
            payload.extend(struct.pack(">d", norm_value))
            payload.extend(self._encode_vector(vector, dimensions))

        response = self._request(_OP_RANGE, bytes(payload))
        hits = response.payload
        self._validate_range_hits(
            hits,
            candidate_count=candidate_count,
            threshold=threshold,
            max_hits=max_hits,
        )
        return hits

    def range_search_many(
        self,
        queries: Sequence[tuple[Sequence[float], float]],
        candidates: Sequence[tuple[Sequence[float], float]],
        similarity_threshold: float,
        *,
        max_total_hits: int = _MAX_RANGE_HITS,
    ) -> list[list[VectorHit]]:
        """Threshold-search many queries against one shared candidate matrix."""
        query_count = len(queries)
        candidate_count = len(candidates)
        threshold = float(similarity_threshold)

        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside supported range")
        if not 1 <= candidate_count <= self.config.max_candidates:
            raise ValueError("candidate count outside supported range")
        if not 1 <= max_total_hits <= _MAX_RANGE_HITS:
            raise ValueError("max_total_hits outside supported range")
        if not math.isfinite(threshold) or not -1.0 <= threshold <= 1.0:
            raise ValueError("similarity_threshold outside [-1, 1]")

        dimensions = len(queries[0][0])
        if not 1 <= dimensions <= self.config.max_dimensions:
            raise ValueError("query dimensions outside supported range")
        if dimensions * (query_count + candidate_count) > self.config.max_elements:
            raise ValueError("vector element count exceeds accelerator bound")

        payload = bytearray(
            _BATCH_RANGE_PREFIX.pack(
                dimensions,
                query_count,
                candidate_count,
                max_total_hits,
                threshold,
            )
        )
        for query, norm in queries:
            if len(query) != dimensions:
                raise ValueError("query dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("query_norm must be finite and positive")
            payload.extend(struct.pack(">d", norm_value))
            payload.extend(self._encode_vector(query, dimensions))
        for vector, norm in candidates:
            if len(vector) != dimensions:
                raise ValueError("candidate dimension mismatch")
            norm_value = float(norm)
            if not math.isfinite(norm_value) or norm_value <= 0:
                raise ValueError("candidate norm must be finite and positive")
            payload.extend(struct.pack(">d", norm_value))
            payload.extend(self._encode_vector(vector, dimensions))

        response = self._request(_OP_BATCH_RANGE, bytes(payload))
        batches = response.payload
        if not isinstance(batches, list) or len(batches) != query_count:
            raise JvmVectorProtocolError("batch range query count mismatch")

        total = 0
        for hits in batches:
            self._validate_range_hits(
                hits,
                candidate_count=candidate_count,
                threshold=threshold,
                max_hits=min(candidate_count, max_total_hits),
            )
            total += len(hits)
            if total > max_total_hits:
                raise JvmVectorProtocolError("batch range result bound exceeded")
        return batches

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
                        _HEADER_REQUEST.pack(_MAGIC, _VERSION, _OP_SHUTDOWN, request_id)
                    )
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
                raise JvmVectorUnavailable("vector accelerator is closed")
            self._ensure_started()
            process = self._process
            assert process is not None and process.stdin is not None
            request_id = self._next_request_id()
            self._requests += 1

            try:
                process.stdin.write(
                    _HEADER_REQUEST.pack(_MAGIC, _VERSION, op, request_id)
                )
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._failed_requests += 1
                self._last_error = f"vector accelerator write failed: {type(exc).__name__}"
                self._terminate_process()
                raise JvmVectorUnavailable(self._diagnostic(self._last_error)) from exc

            try:
                item = self._responses.get(timeout=self.config.response_timeout_seconds)
            except queue.Empty as exc:
                self._failed_requests += 1
                self._timeouts += 1
                self._last_error = "vector accelerator response timed out"
                self._terminate_process()
                raise JvmVectorTimeout(self._diagnostic(self._last_error)) from exc

            if isinstance(item, BaseException):
                self._failed_requests += 1
                self._last_error = str(item)
                self._terminate_process()
                raise JvmVectorUnavailable(self._diagnostic(str(item))) from item
            if item.request_id != request_id or item.op != op:
                self._failed_requests += 1
                self._last_error = "vector response correlation mismatch"
                self._terminate_process()
                raise JvmVectorProtocolError(self._last_error)
            if item.status != _STATUS_OK:
                self._failed_requests += 1
                self._last_error = str(item.payload)
                raise JvmVectorProtocolError(str(item.payload))
            self._successful_requests += 1
            return item

    def _ensure_started(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            return
        self._start_process()

    def _start_process(self) -> None:
        if not self.config.source.is_file():
            message = f"vector accelerator source not found: {self.config.source}"
            self._start_failures += 1
            self._last_error = message
            raise JvmVectorUnavailable(message)
        java = (
            shutil.which(self.config.java_binary)
            if os.path.sep not in self.config.java_binary
            else self.config.java_binary
        )
        if not java or not Path(java).exists():
            message = f"java binary not found: {self.config.java_binary}"
            self._start_failures += 1
            self._last_error = message
            raise JvmVectorUnavailable(message)

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
            raise JvmVectorUnavailable(message) from exc

        self._process = process
        self._starts += 1
        self._reader = threading.Thread(
            target=self._reader_loop,
            args=(process,),
            name="skeleton-jvm-vector-reader",
            daemon=True,
        )
        self._stderr_reader = threading.Thread(
            target=self._stderr_loop,
            args=(process,),
            name="skeleton-jvm-vector-stderr",
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
                    raise JvmVectorProtocolError("invalid vector response header")

                if status != _STATUS_OK:
                    length = _INT.unpack(self._read_exact(process.stdout, _INT.size))[0]
                    if not 0 <= length <= 8192:
                        raise JvmVectorProtocolError("invalid error payload length")
                    message = self._read_exact(process.stdout, length).decode("utf-8", "replace")
                    self._responses.put(_Response(op, status, request_id, message))
                    continue

                payload = self._read_success_payload(process.stdout, op)
                self._responses.put(_Response(op, status, request_id, payload))
        except EOFError:
            if not self._closed:
                return_code = process.poll()
                detail = (
                    "vector accelerator stdout closed"
                    if return_code is None
                    else f"vector accelerator exited with code {return_code}"
                )
                self._responses.put(JvmVectorUnavailable(detail))
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
        if op in {_OP_TOP_K, _OP_RANGE}:
            count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
            if not 0 <= count <= self.config.max_candidates:
                raise JvmVectorProtocolError("invalid hit count")
            hits: list[VectorHit] = []
            for _ in range(count):
                index, similarity = _HIT.unpack(self._read_exact(stream, _HIT.size))
                hits.append(VectorHit(index=index, similarity=similarity))
            return hits
        if op in {_OP_BATCH_TOP_K, _OP_BATCH_RANGE}:
            query_count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
            if not 0 <= query_count <= _MAX_QUERIES:
                raise JvmVectorProtocolError("invalid batch query count")
            batches: list[list[VectorHit]] = []
            for _ in range(query_count):
                count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
                if not 0 <= count <= self.config.max_candidates:
                    raise JvmVectorProtocolError("invalid batch hit count")
                hits: list[VectorHit] = []
                for _ in range(count):
                    index, similarity = _HIT.unpack(
                        self._read_exact(stream, _HIT.size)
                    )
                    hits.append(VectorHit(index=index, similarity=similarity))
                batches.append(hits)
            return batches
        if op == _OP_SHUTDOWN:
            return None
        raise JvmVectorProtocolError(f"unknown response operation: {op}")

    @staticmethod
    def _read_exact(stream: object, size: int) -> bytes:
        read = getattr(stream, "read")
        chunks = bytearray()
        while len(chunks) < size:
            part = read(size - len(chunks))
            if not part:
                raise EOFError("unexpected EOF from vector accelerator")
            chunks.extend(part)
        return bytes(chunks)

    @staticmethod
    def _validate_hits(
        hits: object,
        candidate_count: int,
        top_k: int,
    ) -> None:
        if not isinstance(hits, list):
            raise JvmVectorProtocolError("invalid top-k response")
        if len(hits) != min(top_k, candidate_count) or not all(
            isinstance(hit, VectorHit) for hit in hits
        ):
            raise JvmVectorProtocolError("invalid top-k response")
        seen: set[int] = set()
        previous: VectorHit | None = None
        for hit in hits:
            if not 0 <= hit.index < candidate_count:
                raise JvmVectorProtocolError("hit index outside candidate range")
            if hit.index in seen:
                raise JvmVectorProtocolError("duplicate hit index")
            if not math.isfinite(hit.similarity):
                raise JvmVectorProtocolError("non-finite similarity")
            if hit.similarity < -1.000000000001 or hit.similarity > 1.000000000001:
                raise JvmVectorProtocolError("cosine similarity outside supported range")
            if previous is not None and (
                hit.similarity > previous.similarity
                or (
                    hit.similarity == previous.similarity
                    and hit.index < previous.index
                )
            ):
                raise JvmVectorProtocolError("top-k response is not stably ordered")
            seen.add(hit.index)
            previous = hit

    @staticmethod
    def _validate_range_hits(
        hits: object,
        *,
        candidate_count: int,
        threshold: float,
        max_hits: int,
    ) -> None:
        if not isinstance(hits, list) or len(hits) > max_hits:
            raise JvmVectorProtocolError("invalid range-search response")
        seen: set[int] = set()
        previous: VectorHit | None = None
        for hit in hits:
            if not isinstance(hit, VectorHit):
                raise JvmVectorProtocolError("invalid range-search hit")
            if not 0 <= hit.index < candidate_count:
                raise JvmVectorProtocolError("range hit index outside candidate range")
            if hit.index in seen:
                raise JvmVectorProtocolError("duplicate range hit index")
            if not math.isfinite(hit.similarity):
                raise JvmVectorProtocolError("non-finite range similarity")
            if hit.similarity + 1e-12 < threshold:
                raise JvmVectorProtocolError("range hit below requested threshold")
            if hit.similarity < -1.000000000001 or hit.similarity > 1.000000000001:
                raise JvmVectorProtocolError("range cosine outside supported range")
            if previous is not None and (
                hit.similarity > previous.similarity
                or (
                    hit.similarity == previous.similarity
                    and hit.index < previous.index
                )
            ):
                raise JvmVectorProtocolError("range response is not stably ordered")
            seen.add(hit.index)
            previous = hit

    @staticmethod
    def _encode_vector(vector: Sequence[float], dimensions: int) -> bytes:
        if len(vector) != dimensions:
            raise ValueError("vector dimension mismatch")
        doubles = array.array("d", vector)
        if sys.byteorder == "little":
            doubles.byteswap()
        return doubles.tobytes()

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
        return f"{message}; java stderr: {' | '.join(self._stderr_tail)}"


_default_lock = threading.Lock()
_default_accelerator: JvmVectorAccelerator | None = None


def get_default_vector_accelerator() -> JvmVectorAccelerator:
    global _default_accelerator
    with _default_lock:
        if _default_accelerator is None:
            _default_accelerator = JvmVectorAccelerator()
        return _default_accelerator


def close_default_vector_accelerator() -> None:
    global _default_accelerator
    with _default_lock:
        accelerator = _default_accelerator
        _default_accelerator = None
    if accelerator is not None:
        accelerator.close()


atexit.register(close_default_vector_accelerator)
