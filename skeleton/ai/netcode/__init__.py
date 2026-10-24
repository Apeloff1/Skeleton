"""Game netcode for the #807 network lane (wave 1: B061-B064).

* :mod:`.contracts`   - B061 versioned framing, message/session contracts, codecs.
* :mod:`.transport`   - B061 pluggable transports (in-memory, loopback UDP/TCP,
  adapter over the realtime SSE parser).
* :mod:`.replication` - B062 server-authoritative snapshots, delta compression,
  per-tick bandwidth budget, deterministic lossy link.
* :mod:`.lobby`       - B063 lobby lifecycle, permissions, invites, abuse controls.
* :mod:`.server`      - B064 dedicated headless server (``python -m skeleton.netcode``).

``skeleton/ai/netcode`` is a byte-identical mirror (relative imports only).
"""
from .contracts import (PROTOCOL_VERSION, MIN_COMPATIBLE_VERSION, BinaryFrameCodec, Codec,
                        FrameError, Message, MessageKind, Session, StreamDecoder)
from .transport import InMemoryTransport, SSEMessageAdapter, TcpLoopbackTransport, Transport, UdpLoopbackTransport
from .replication import (BandwidthBudget, ClientReplica, LossyLink, ServerReplicator, Snapshot,
                          decode_delta, encode_delta)
from .lobby import InviteCodec, InviteError, Lobby, LobbyError, LobbyState, RateLimiter, Role
from .server import HeadlessServer, ServerConfig, build_manifest

__all__ = [
    "PROTOCOL_VERSION", "MIN_COMPATIBLE_VERSION", "BinaryFrameCodec", "Codec", "FrameError", "Message",
    "MessageKind", "Session", "StreamDecoder", "InMemoryTransport", "SSEMessageAdapter",
    "TcpLoopbackTransport", "Transport", "UdpLoopbackTransport", "BandwidthBudget", "ClientReplica",
    "LossyLink", "ServerReplicator", "Snapshot", "decode_delta", "encode_delta", "InviteCodec",
    "InviteError", "Lobby", "LobbyError", "LobbyState", "RateLimiter", "Role", "HeadlessServer",
    "ServerConfig", "build_manifest",
]
