"""Private socket transport and native batch policy source regressions."""
import os
import socket
import threading
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference.resident_gguf_batch import (
    ResidentBatchPolicy, _PrivateConnection, _strict_object,
)


def test_resident_batch_policy_refuses_unbounded_or_cpu_profiles():
    for override in ({"gpu_layers":0}, {"slots":1}, {"slots":33},
                     {"microbatch_tokens":1024}, {"context_per_slot":131073},
                     {"flash_attention":"unknown"}):
        values = dict(slots=2, context_per_slot=1024, gpu_layers=1, max_memory_bytes=1024**3)
        values.update(override)
        with pytest.raises(ValueError):
            ResidentBatchPolicy(**values)


def test_duplicate_server_json_fields_denied():
    with pytest.raises(ValueError, match="duplicate"):
        _strict_object([("tokens", []), ("tokens", [1])])


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux peer credentials required")
def test_private_connection_validates_pid_before_transmitting(tmp_path):
    endpoint = tmp_path / "local.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    listener.listen(2)
    seen = []
    def handle():
        with listener:
            for _ in range(2):
                conn, _ = listener.accept()
                with conn:
                    seen.append(conn.recv(64))
    worker = threading.Thread(target=handle)
    worker.start()
    try:
        wrong = _PrivateConnection(endpoint, os.getpid()+1, timeout=1)
        with pytest.raises(PermissionError):
            wrong.connect()
        right = _PrivateConnection(endpoint, os.getpid(), timeout=1)
        right.connect()
        right.sock.sendall(b"local-only")
        right.close()
    finally:
        worker.join(timeout=2)
    assert seen == [b"", b"local-only"]
