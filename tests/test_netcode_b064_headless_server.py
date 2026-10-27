"""B064: server artifacts are reproducible, minimal, observable and version-compatible with clients."""
import ast
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.netcode.contracts import MIN_COMPATIBLE_VERSION, PROTOCOL_VERSION, BinaryFrameCodec, Message, MessageKind
from skeleton.netcode.replication import ClientReplica
from skeleton.netcode.server import HeadlessServer, ServerConfig, build_manifest, hello_payload
from skeleton.netcode.transport import InMemoryTransport

ROOT = Path(__file__).resolve().parents[1]
CODEC = BinaryFrameCodec()


def _client(srv, cid, version=PROTOCOL_VERSION, min_version=MIN_COMPATIBLE_VERSION):
    c, s = InMemoryTransport.pair()
    srv.connect(cid, s)
    c.send(CODEC.encode(Message(MessageKind.HELLO, hello_payload(version, min_version), seq=1, version=version)))
    return c


def _drain(t):
    out = []
    while (raw := t.recv()) is not None:
        out.append(CODEC.decode(raw))
    return out


def test_b064_handshake_accepts_compatible_client():
    srv = HeadlessServer(ServerConfig(entities=4))
    c = _client(srv, "a")
    srv.tick()
    kinds = [m.kind for m in _drain(c)]
    assert kinds[0] is MessageKind.WELCOME and MessageKind.SNAPSHOT in kinds


@pytest.mark.parametrize("ver,minv", [(PROTOCOL_VERSION + 1, PROTOCOL_VERSION + 1), (MIN_COMPATIBLE_VERSION - 1, 0)])
def test_b064_handshake_rejects_incompatible_version_cleanly(ver, minv):
    srv = HeadlessServer(ServerConfig())
    c = _client(srv, "old", ver, minv)
    srv.tick()
    msgs = _drain(c)
    assert [(m.kind, m.payload) for m in msgs] == [(MessageKind.REJECT, b"incompatible_version")]
    assert "old" not in srv.accepted and srv.metrics["handshakes_rejected"] == 1
    srv.tick()  # rejected client no longer serviced
    assert _drain(c) == []


def test_b064_rejects_when_full_and_counts_malformed():
    srv = HeadlessServer(ServerConfig(max_clients=1))
    _client(srv, "a")
    c2 = _client(srv, "b")
    srv.transports["a"].peer.send(b"junk")  # garbage from accepted-to-be client
    srv.tick()
    assert _drain(c2)[0].payload == b"server_full"
    assert srv.metrics["frames_malformed"] == 1


def test_b064_tick_loop_is_deterministic():
    def run():
        srv = HeadlessServer(ServerConfig(seed=9, entities=8))
        c = _client(srv, "a")
        for _ in range(50):
            srv.tick()
        return srv.state_digest(), [CODEC.encode(m) for m in _drain(c)]
    assert run() == run()


def test_b064_client_replica_tracks_server_state():
    srv = HeadlessServer(ServerConfig(seed=3, entities=6))
    c = _client(srv, "a")
    cli = ClientReplica()
    for _ in range(30):
        srv.tick()
        for m in _drain(c):
            if m.kind is MessageKind.SNAPSHOT and (t := cli.receive(m.payload)) is not None:
                c.send(CODEC.encode(Message(MessageKind.ACK, struct.pack(">I", t), seq=2)))
    assert cli.state == srv.repl.state


def test_b064_health_metrics_are_observable():
    srv = HeadlessServer(ServerConfig(entities=2))
    _client(srv, "a")
    h = srv.run(realtime=False, max_ticks=5)
    assert h["status"] == "ok" and h["tick"] == 5 and h["protocol_version"] == PROTOCOL_VERSION
    m = h["metrics"]
    assert m["ticks"] == 5 and m["clients"] == 1 and m["handshakes_ok"] == 1 and m["bytes_out"] > 0


def test_b064_config_from_env_and_args_precedence():
    cfg = ServerConfig.from_sources(["--tick-rate", "60"], {"SKELETON_NET_TICK_RATE": "20", "SKELETON_NET_SEED": "5"})
    assert cfg.tick_rate == 60 and cfg.seed == 5
    with pytest.raises(ValueError):
        ServerConfig(tick_rate=0)


def test_b064_manifest_is_reproducible():
    a, b = build_manifest(), build_manifest()
    assert a == b and len(a["digest"]) == 64 and a["dependencies"] == []


def test_b064_server_is_minimal_stdlib_only():
    pkg = ROOT / "skeleton" / "netcode"
    allowed = set(sys.stdlib_module_names) | {"skeleton"}
    for p in pkg.glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for n in names:
                assert n.split(".")[0] in allowed, (p.name, n)


def test_b064_python_dash_m_entry_point_runs_headless():
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    out = subprocess.run([sys.executable, "-m", "skeleton.netcode", "--ticks", "10", "--seed", "1"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    assert report["tick"] == 10 and report["config"]["seed"] == 1
    man = subprocess.run([sys.executable, "-m", "skeleton.netcode", "--manifest"], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=60)
    assert json.loads(man.stdout) == build_manifest()


def test_b064_ai_mirror_is_in_sync():
    a, b = ROOT / "skeleton" / "netcode", ROOT / "skeleton" / "ai" / "netcode"
    names = sorted(p.name for p in a.glob("*.py"))
    assert names == sorted(p.name for p in b.glob("*.py"))
    for n in names:
        assert (a / n).read_bytes() == (b / n).read_bytes(), n
