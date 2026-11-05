"""Length-framed canonical JSON over anonymous private pipes.

No newline framing: model text may contain arbitrary newlines, null-equivalents
and Unicode. The receiver checks the length before allocation and treats EOF
as a failed native invocation, never a successful empty response.
"""
from __future__ import annotations
import json
import os
import select
import struct
import time
from .contracts import IsolationProtocolError, IsolationUnavailable

_HEADER = struct.Struct('!I')


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for k, v in pairs:
        if k in result:
            raise IsolationProtocolError('duplicate IPC JSON key')
        result[k] = v
    return result


def encode(data: dict, ceiling: int = 1_048_576) -> bytes:
    if not isinstance(data, dict):
        raise IsolationProtocolError('IPC object required')
    try:
        blob = json.dumps(data, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf8', 'strict')
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise IsolationProtocolError('IPC payload is not canonical JSON') from exc
    if len(blob) == 0 or len(blob) > ceiling:
        raise IsolationProtocolError('IPC frame exceeds bounded payload')
    return _HEADER.pack(len(blob)) + blob


def decode(data: bytes, ceiling: int = 1_048_576) -> dict:
    if not isinstance(data, bytes) or not 0 < len(data) <= ceiling:
        raise IsolationProtocolError('IPC decoded payload length invalid')
    try:
        obj = json.loads(data.decode('utf8', 'strict'), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(IsolationProtocolError('nonfinite IPC number')))
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise IsolationProtocolError('invalid IPC JSON') from exc
    if not isinstance(obj, dict):
        raise IsolationProtocolError('IPC root must be an object')
    return obj


def _remaining(deadline_ns: int) -> float:
    remaining_ns = deadline_ns - time.monotonic_ns()
    if remaining_ns <= 0:
        raise IsolationUnavailable('native IPC deadline expired')
    return remaining_ns / 1_000_000_000


def read_exact(fd: int, size: int, deadline_ns: int) -> bytes:
    if type(size) is not int or size < 0 or size > 2_097_152:
        raise IsolationProtocolError('IPC read bound invalid')
    result = bytearray()
    while len(result) < size:
        try:
            ready, _, _ = select.select([fd], [], [], _remaining(deadline_ns))
        except (OSError, ValueError) as exc:
            raise IsolationUnavailable('native IPC read unavailable') from exc
        if not ready:
            raise IsolationUnavailable('native IPC read deadline')
        try:
            chunk = os.read(fd, min(size - len(result), 65536))
        except InterruptedError:
            continue
        except OSError as exc:
            raise IsolationUnavailable('native IPC read failed') from exc
        if not chunk:
            raise IsolationUnavailable('native IPC closed before complete response')
        result.extend(chunk)
    return bytes(result)


def read_frame(fd: int, deadline_ns: int, ceiling: int = 1_048_576) -> dict:
    header = read_exact(fd, _HEADER.size, deadline_ns)
    (size,) = _HEADER.unpack(header)
    if not 0 < size <= ceiling:
        raise IsolationProtocolError('native IPC frame declared invalid size')
    return decode(read_exact(fd, size, deadline_ns), ceiling)


def write_exact(fd: int, data: bytes, deadline_ns: int) -> None:
    view = memoryview(data)
    while view:
        try:
            _, ready, _ = select.select([], [fd], [], _remaining(deadline_ns))
        except (OSError, ValueError) as exc:
            raise IsolationUnavailable('native IPC write unavailable') from exc
        if not ready:
            raise IsolationUnavailable('native IPC write deadline')
        try:
            n = os.write(fd, view[:65536])
        except InterruptedError:
            continue
        except (BrokenPipeError, OSError) as exc:
            raise IsolationUnavailable('native IPC write failed') from exc
        if n <= 0:
            raise IsolationUnavailable('native IPC write returned no bytes')
        view = view[n:]


def write_frame(fd: int, payload: dict, deadline_ns: int, ceiling: int = 1_048_576) -> None:
    write_exact(fd, encode(payload, ceiling), deadline_ns)
