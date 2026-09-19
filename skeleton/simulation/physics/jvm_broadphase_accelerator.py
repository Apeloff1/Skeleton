"""Optional Java finite-AABB broad-phase accelerator.

The physics engine remains authoritative. This helper knows only finite AABBs,
one dynamic/static bit per candidate, and stable integer indices. Infinite
planes, body IDs, narrow-phase shape logic, manifolds, caches, and solving stay
inside Python.
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

from .math3d import AABB
from .queries import Ray

_MAGIC = 0x534B4250
_VERSION = 1
_OP_PING = 1
_OP_PAIRS = 2
_OP_SHUTDOWN = 3
_OP_QUERY_AABBS = 4
_OP_RAY_AABBS = 5
_OP_SPHERE_CAST_AABBS = 6
_STATUS_OK = 0
_MAX_BODIES = 100_000
_MAX_PAIRS = 1_000_000
_MAX_QUERIES = 4096
_MAX_QUERY_HITS = 1_000_000
_MAX_SPATIAL_TESTS = 50_000_000
_HEADER_REQUEST = struct.Struct(">IhBq")
_HEADER_RESPONSE = struct.Struct(">IhBBq")
_INT = struct.Struct(">i")
_PING = struct.Struct(">qi")
_REQUEST_PREFIX = struct.Struct(">iid")
_QUERY_PREFIX = struct.Struct(">iii")
_SPHERE_QUERY_PREFIX = struct.Struct(">iiid")
_BOX = struct.Struct(">?6d")
_BOUNDS = struct.Struct(">6d")
_RAY = struct.Struct(">7d")
_PAIR = struct.Struct(">ii")


class JvmBroadPhaseError(RuntimeError):
    """Base class for optional broad-phase accelerator failures."""


class JvmBroadPhaseUnavailable(JvmBroadPhaseError):
    """Raised when Java or the source launcher cannot start."""


class JvmBroadPhaseProtocolError(JvmBroadPhaseError):
    """Raised when the JVM rejects or malforms a broad-phase frame."""


class JvmBroadPhaseTimeout(JvmBroadPhaseError):
    """Raised when a live JVM misses the response deadline."""


@dataclass(frozen=True, slots=True)
class BroadPhaseIndexPair:
    left: int
    right: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.right <= self.left:
            raise ValueError("broad-phase indices must be strictly ordered")


@dataclass(frozen=True, slots=True)
class BroadPhaseAcceleratorStatus:
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
class JvmBroadPhaseConfig:
    java_binary: str
    source: Path
    response_timeout_seconds: float = 15.0
    minimum_bodies: int = 2048
    minimum_spatial_tests: int = 16_384
    max_bodies: int = _MAX_BODIES
    max_pairs: int = _MAX_PAIRS

    def __post_init__(self) -> None:
        if not self.java_binary:
            raise ValueError("java_binary must be non-empty")
        if self.response_timeout_seconds <= 0:
            raise ValueError("response_timeout_seconds must be positive")
        if not 1 <= self.minimum_bodies <= self.max_bodies:
            raise ValueError("minimum_bodies outside supported range")
        if not 1 <= self.minimum_spatial_tests <= _MAX_SPATIAL_TESTS:
            raise ValueError("minimum_spatial_tests outside supported range")
        if not 1 <= self.max_bodies <= _MAX_BODIES:
            raise ValueError("max_bodies outside supported range")
        if not 1 <= self.max_pairs <= _MAX_PAIRS:
            raise ValueError("max_pairs outside supported range")

    @classmethod
    def discover(cls) -> "JvmBroadPhaseConfig":
        java_binary = os.environ.get("SKELETON_JAVA_BIN") or shutil.which("java") or "java"
        root = Path(__file__).resolve().parents[3]
        source = Path(
            os.environ.get(
                "SKELETON_JVM_BROADPHASE_SOURCE",
                root / "java-accelerators" / "physics" / "BroadPhaseMain.java",
            )
        )
        timeout = float(os.environ.get("SKELETON_JVM_BROADPHASE_TIMEOUT", "15"))
        minimum = int(os.environ.get("SKELETON_JVM_BROADPHASE_MIN_BODIES", "2048"))
        minimum_spatial = int(
            os.environ.get(
                "SKELETON_JVM_BROADPHASE_MIN_SPATIAL_TESTS",
                "16384",
            )
        )
        return cls(
            java_binary=java_binary,
            source=source,
            response_timeout_seconds=timeout,
            minimum_bodies=minimum,
            minimum_spatial_tests=minimum_spatial,
        )


@dataclass(slots=True)
class _Response:
    op: int
    status: int
    request_id: int
    payload: object


class JvmBroadPhaseAccelerator:
    """Persistent stdio client for the bounded Java AABB sweep."""

    def __init__(self, config: JvmBroadPhaseConfig | None = None) -> None:
        self.config = config or JvmBroadPhaseConfig.discover()
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
    def minimum_bodies(self) -> int:
        return self.config.minimum_bodies

    @property
    def minimum_spatial_tests(self) -> int:
        return self.config.minimum_spatial_tests

    def __enter__(self) -> "JvmBroadPhaseAccelerator":
        self.ping()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def status(self) -> BroadPhaseAcceleratorStatus:
        process = self._process
        running = process is not None and process.poll() is None
        return BroadPhaseAcceleratorStatus(
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
            raise JvmBroadPhaseProtocolError("ping response type mismatch")
        _server_nanos, processors = response.payload
        self._server_processors = int(processors)
        return int(processors)

    def compute_pairs(
        self,
        bodies: Sequence[tuple[AABB, bool]],
        *,
        max_pairs: int,
        epsilon: float,
    ) -> list[BroadPhaseIndexPair]:
        count = len(bodies)
        if count > self.config.max_bodies:
            raise ValueError("body count exceeds accelerator bound")
        if not 1 <= max_pairs <= min(self.config.max_pairs, _MAX_PAIRS):
            raise ValueError("max_pairs outside accelerator bound")
        if not math.isfinite(epsilon) or not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon outside supported range")

        payload = bytearray(_REQUEST_PREFIX.pack(count, max_pairs, epsilon))
        for bounds, dynamic in bodies:
            if not isinstance(bounds, AABB):
                raise TypeError("broad-phase bounds must be AABB")
            if not isinstance(dynamic, bool):
                raise TypeError("dynamic flag must be bool")
            payload.extend(
                _BOX.pack(
                    dynamic,
                    bounds.minimum.x,
                    bounds.minimum.y,
                    bounds.minimum.z,
                    bounds.maximum.x,
                    bounds.maximum.y,
                    bounds.maximum.z,
                )
            )

        response = self._request(_OP_PAIRS, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmBroadPhaseProtocolError("pair response type mismatch")
        pairs = response.payload
        self._validate_pairs(pairs, count, max_pairs)
        return pairs

    def query_overlaps_many(
        self,
        body_bounds: Sequence[AABB],
        queries: Sequence[AABB],
        *,
        max_total_hits: int = _MAX_QUERY_HITS,
    ) -> list[list[int]]:
        """Return stable body indices overlapping each query AABB."""
        body_count = len(body_bounds)
        query_count = len(queries)
        if body_count > self.config.max_bodies:
            raise ValueError("body count exceeds accelerator bound")
        if not 1 <= query_count <= _MAX_QUERIES:
            raise ValueError("query count outside accelerator bound")
        if not 1 <= max_total_hits <= _MAX_QUERY_HITS:
            raise ValueError("max_total_hits outside accelerator bound")
        if body_count * query_count > _MAX_SPATIAL_TESTS:
            raise ValueError("spatial test bound exceeded")

        payload = bytearray(
            _QUERY_PREFIX.pack(body_count, query_count, max_total_hits)
        )
        for bounds in body_bounds:
            payload.extend(self._encode_bounds(bounds))
        for bounds in queries:
            payload.extend(self._encode_bounds(bounds))

        response = self._request(_OP_QUERY_AABBS, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmBroadPhaseProtocolError("AABB query response type mismatch")
        batches = response.payload
        self._validate_index_batches(
            batches,
            batch_count=query_count,
            body_count=body_count,
            max_total=max_total_hits,
            label="AABB query",
        )
        return batches

    def ray_candidates_many(
        self,
        body_bounds: Sequence[AABB],
        rays: Sequence[Ray],
        *,
        max_total_candidates: int = _MAX_QUERY_HITS,
    ) -> list[list[int]]:
        """Return stable finite-body candidate indices for each ray."""
        body_count = len(body_bounds)
        ray_count = len(rays)
        if body_count > self.config.max_bodies:
            raise ValueError("body count exceeds accelerator bound")
        if not 1 <= ray_count <= _MAX_QUERIES:
            raise ValueError("ray count outside accelerator bound")
        if not 1 <= max_total_candidates <= _MAX_QUERY_HITS:
            raise ValueError("max_total_candidates outside accelerator bound")
        if body_count * ray_count > _MAX_SPATIAL_TESTS:
            raise ValueError("spatial test bound exceeded")

        payload = bytearray(
            _QUERY_PREFIX.pack(
                body_count,
                ray_count,
                max_total_candidates,
            )
        )
        for bounds in body_bounds:
            payload.extend(self._encode_bounds(bounds))
        for ray in rays:
            if not isinstance(ray, Ray):
                raise TypeError("ray batch must contain Ray values")
            payload.extend(
                _RAY.pack(
                    ray.origin.x,
                    ray.origin.y,
                    ray.origin.z,
                    ray.direction.x,
                    ray.direction.y,
                    ray.direction.z,
                    ray.max_distance,
                )
            )

        response = self._request(_OP_RAY_AABBS, bytes(payload))
        if not isinstance(response.payload, list):
            raise JvmBroadPhaseProtocolError("ray candidate response type mismatch")
        batches = response.payload
        self._validate_index_batches(
            batches,
            batch_count=ray_count,
            body_count=body_count,
            max_total=max_total_candidates,
            label="ray candidate",
        )
        return batches

    def sphere_cast_candidates_many(
        self,
        body_bounds: Sequence[AABB],
        rays: Sequence[Ray],
        radius: float,
        *,
        max_total_candidates: int = _MAX_QUERY_HITS,
    ) -> list[list[int]]:
        """Return stable finite-body coarse candidates for sphere casts."""
        body_count = len(body_bounds)
        ray_count = len(rays)
        radius_value = float(radius)
        if not math.isfinite(radius_value) or radius_value <= 0.0:
            raise ValueError("sphere cast radius must be finite and positive")
        if body_count > self.config.max_bodies:
            raise ValueError("body count exceeds accelerator bound")
        if not 1 <= ray_count <= _MAX_QUERIES:
            raise ValueError("ray count outside accelerator bound")
        if not 1 <= max_total_candidates <= _MAX_QUERY_HITS:
            raise ValueError("max_total_candidates outside accelerator bound")
        if body_count * ray_count > _MAX_SPATIAL_TESTS:
            raise ValueError("spatial test bound exceeded")

        payload = bytearray(
            _SPHERE_QUERY_PREFIX.pack(
                body_count,
                ray_count,
                max_total_candidates,
                radius_value,
            )
        )
        for bounds in body_bounds:
            payload.extend(self._encode_bounds(bounds))
        for ray in rays:
            if not isinstance(ray, Ray):
                raise TypeError("sphere cast batch must contain Ray values")
            payload.extend(
                _RAY.pack(
                    ray.origin.x,
                    ray.origin.y,
                    ray.origin.z,
                    ray.direction.x,
                    ray.direction.y,
                    ray.direction.z,
                    ray.max_distance,
                )
            )

        response = self._request(
            _OP_SPHERE_CAST_AABBS,
            bytes(payload),
        )
        if not isinstance(response.payload, list):
            raise JvmBroadPhaseProtocolError(
                "sphere-cast candidate response type mismatch"
            )
        batches = response.payload
        self._validate_index_batches(
            batches,
            batch_count=ray_count,
            body_count=body_count,
            max_total=max_total_candidates,
            label="sphere-cast candidate",
        )
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
                raise JvmBroadPhaseUnavailable("broad-phase accelerator is closed")
            self._ensure_started()
            process = self._process
            assert process is not None and process.stdin is not None
            request_id = self._next_request_id()
            self._requests += 1
            try:
                process.stdin.write(_HEADER_REQUEST.pack(_MAGIC, _VERSION, op, request_id))
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._failed_requests += 1
                self._last_error = f"broad-phase accelerator write failed: {type(exc).__name__}"
                self._terminate_process()
                raise JvmBroadPhaseUnavailable(self._diagnostic(self._last_error)) from exc

            try:
                item = self._responses.get(timeout=self.config.response_timeout_seconds)
            except queue.Empty as exc:
                self._failed_requests += 1
                self._timeouts += 1
                self._last_error = "broad-phase accelerator response timed out"
                self._terminate_process()
                raise JvmBroadPhaseTimeout(self._diagnostic(self._last_error)) from exc

            if isinstance(item, BaseException):
                self._failed_requests += 1
                self._last_error = str(item)
                self._terminate_process()
                raise JvmBroadPhaseUnavailable(self._diagnostic(str(item))) from item
            if item.request_id != request_id or item.op != op:
                self._failed_requests += 1
                self._last_error = "broad-phase response correlation mismatch"
                self._terminate_process()
                raise JvmBroadPhaseProtocolError(self._last_error)
            if item.status != _STATUS_OK:
                self._failed_requests += 1
                self._last_error = str(item.payload)
                raise JvmBroadPhaseProtocolError(str(item.payload))
            self._successful_requests += 1
            return item

    def _ensure_started(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            return
        self._start_process()

    def _start_process(self) -> None:
        if not self.config.source.is_file():
            message = f"broad-phase accelerator source not found: {self.config.source}"
            self._start_failures += 1
            self._last_error = message
            raise JvmBroadPhaseUnavailable(message)
        java = (
            shutil.which(self.config.java_binary)
            if os.path.sep not in self.config.java_binary
            else self.config.java_binary
        )
        if not java or not Path(java).exists():
            message = f"java binary not found: {self.config.java_binary}"
            self._start_failures += 1
            self._last_error = message
            raise JvmBroadPhaseUnavailable(message)

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
            raise JvmBroadPhaseUnavailable(message) from exc

        self._process = process
        self._starts += 1
        self._reader = threading.Thread(
            target=self._reader_loop,
            args=(process,),
            name="skeleton-jvm-broadphase-reader",
            daemon=True,
        )
        self._stderr_reader = threading.Thread(
            target=self._stderr_loop,
            args=(process,),
            name="skeleton-jvm-broadphase-stderr",
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
                    raise JvmBroadPhaseProtocolError("invalid broad-phase response header")

                if status != _STATUS_OK:
                    length = _INT.unpack(self._read_exact(process.stdout, _INT.size))[0]
                    if not 0 <= length <= 8192:
                        raise JvmBroadPhaseProtocolError("invalid error payload length")
                    message = self._read_exact(process.stdout, length).decode("utf-8", "replace")
                    self._responses.put(_Response(op, status, request_id, message))
                    continue

                payload = self._read_success_payload(process.stdout, op)
                self._responses.put(_Response(op, status, request_id, payload))
        except EOFError:
            if not self._closed:
                return_code = process.poll()
                detail = (
                    "broad-phase accelerator stdout closed"
                    if return_code is None
                    else f"broad-phase accelerator exited with code {return_code}"
                )
                self._responses.put(JvmBroadPhaseUnavailable(detail))
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
        if op == _OP_PAIRS:
            count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
            if not 0 <= count <= self.config.max_pairs:
                raise JvmBroadPhaseProtocolError("invalid pair count")
            pairs: list[BroadPhaseIndexPair] = []
            for _ in range(count):
                left, right = _PAIR.unpack(self._read_exact(stream, _PAIR.size))
                try:
                    pairs.append(BroadPhaseIndexPair(left, right))
                except ValueError as exc:
                    raise JvmBroadPhaseProtocolError(str(exc)) from exc
            return pairs
        if op in {
            _OP_QUERY_AABBS,
            _OP_RAY_AABBS,
            _OP_SPHERE_CAST_AABBS,
        }:
            batch_count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
            if not 0 <= batch_count <= _MAX_QUERIES:
                raise JvmBroadPhaseProtocolError("invalid spatial batch count")
            batches: list[list[int]] = []
            total = 0
            for _ in range(batch_count):
                count = _INT.unpack(self._read_exact(stream, _INT.size))[0]
                if not 0 <= count <= self.config.max_bodies:
                    raise JvmBroadPhaseProtocolError("invalid spatial hit count")
                hits: list[int] = []
                for _ in range(count):
                    index = _INT.unpack(
                        self._read_exact(stream, _INT.size)
                    )[0]
                    hits.append(index)
                    total += 1
                    if total > _MAX_QUERY_HITS:
                        raise JvmBroadPhaseProtocolError(
                            "spatial response exceeds hard hit bound"
                        )
                batches.append(hits)
            return batches
        if op == _OP_SHUTDOWN:
            return None
        raise JvmBroadPhaseProtocolError(f"unknown response operation: {op}")

    @staticmethod
    def _read_exact(stream: object, size: int) -> bytes:
        read = getattr(stream, "read")
        chunks = bytearray()
        while len(chunks) < size:
            part = read(size - len(chunks))
            if not part:
                raise EOFError("unexpected EOF from broad-phase accelerator")
            chunks.extend(part)
        return bytes(chunks)

    @staticmethod
    def _encode_bounds(bounds: AABB) -> bytes:
        if not isinstance(bounds, AABB):
            raise TypeError("spatial query bounds must be AABB")
        return _BOUNDS.pack(
            bounds.minimum.x,
            bounds.minimum.y,
            bounds.minimum.z,
            bounds.maximum.x,
            bounds.maximum.y,
            bounds.maximum.z,
        )

    @staticmethod
    def _validate_index_batches(
        batches: object,
        *,
        batch_count: int,
        body_count: int,
        max_total: int,
        label: str,
    ) -> None:
        if not isinstance(batches, list) or len(batches) != batch_count:
            raise JvmBroadPhaseProtocolError(
                f"{label} batch count mismatch"
            )
        total = 0
        for hits in batches:
            if not isinstance(hits, list):
                raise JvmBroadPhaseProtocolError(
                    f"invalid {label} batch"
                )
            previous = -1
            for index in hits:
                if not isinstance(index, int) or not 0 <= index < body_count:
                    raise JvmBroadPhaseProtocolError(
                        f"{label} index outside body range"
                    )
                if index <= previous:
                    raise JvmBroadPhaseProtocolError(
                        f"{label} indices are not strictly ordered"
                    )
                previous = index
                total += 1
                if total > max_total:
                    raise JvmBroadPhaseProtocolError(
                        f"{label} total-hit bound exceeded"
                    )

    @staticmethod
    def _validate_pairs(
        pairs: list[BroadPhaseIndexPair],
        body_count: int,
        max_pairs: int,
    ) -> None:
        if len(pairs) > max_pairs:
            raise JvmBroadPhaseProtocolError("pair count exceeds requested bound")
        previous: BroadPhaseIndexPair | None = None
        seen: set[tuple[int, int]] = set()
        for pair in pairs:
            if pair.right >= body_count:
                raise JvmBroadPhaseProtocolError("pair index outside body range")
            key = (pair.left, pair.right)
            if key in seen:
                raise JvmBroadPhaseProtocolError("duplicate broad-phase pair")
            if previous is not None and key <= (previous.left, previous.right):
                raise JvmBroadPhaseProtocolError("broad-phase pairs are not strictly ordered")
            seen.add(key)
            previous = pair

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
_default_accelerator: JvmBroadPhaseAccelerator | None = None


def get_default_broadphase_accelerator() -> JvmBroadPhaseAccelerator:
    global _default_accelerator
    with _default_lock:
        if _default_accelerator is None:
            _default_accelerator = JvmBroadPhaseAccelerator()
        return _default_accelerator


def close_default_broadphase_accelerator() -> None:
    global _default_accelerator
    with _default_lock:
        accelerator = _default_accelerator
        _default_accelerator = None
    if accelerator is not None:
        accelerator.close()


atexit.register(close_default_broadphase_accelerator)
