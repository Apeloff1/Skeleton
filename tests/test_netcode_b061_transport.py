"""B061: transport is isolated behind stable session/message contracts with fuzzable parsers."""
import random
import struct

import pytest

from skeleton.netcode.contracts import (FRAME_OVERHEAD, MAX_PAYLOAD, BinaryFrameCodec, FrameError, Message,
                                        MessageKind, Session, StreamDecoder)
from skeleton.netcode.transport import InMemoryTransport, SSEMessageAdapter, TcpLoopbackTransport, UdpLoopbackTransport

CODEC = BinaryFrameCodec()


def _msg(i=1, payload=b"hello"):
    return Message(MessageKind.INPUT, payload, channel=3, seq=i, ack=i - 1)


def test_b061_frame_roundtrip_is_stable_and_versioned():
    m = _msg()
    data = CODEC.encode(m)
    assert data[:2] == b"SK" and struct.unpack(">H", data[2:4])[0] == m.version
    assert CODEC.decode(data) == m
    assert len(data) == FRAME_OVERHEAD + 5


@pytest.mark.parametrize("bad", [b"", b"SK", b"XX" + b"\0" * 30])
def test_b061_parser_rejects_malformed_frames(bad):
    with pytest.raises(FrameError):
        CODEC.decode(bad)


def test_b061_parser_rejects_oversize_and_corruption():
    with pytest.raises(FrameError):
        Message(MessageKind.INPUT, b"x" * (MAX_PAYLOAD + 1))
    data = bytearray(CODEC.encode(_msg()))
    data[-6] ^= 0xFF
    with pytest.raises(FrameError):
        CODEC.decode(bytes(data))


def test_b061_fuzz_frame_parser_only_raises_frame_error():
    rng = random.Random(807061)
    good = CODEC.encode(_msg(payload=b"abcdefgh"))
    for _ in range(5000):
        mode = rng.randrange(3)
        if mode == 0:
            blob = bytes(rng.randrange(256) for _ in range(rng.randrange(64)))
        elif mode == 1:
            b = bytearray(good)
            for _ in range(rng.randint(1, 4)):
                b[rng.randrange(len(b))] = rng.randrange(256)
            blob = bytes(b)
        else:
            blob = good[: rng.randrange(len(good))]
        try:
            m = CODEC.decode(blob)
        except FrameError:
            continue
        assert CODEC.encode(m) == blob  # anything accepted must be canonical


def test_b061_fuzz_stream_decoder_splits_anywhere():
    rng = random.Random(61)
    frames = [CODEC.encode(_msg(i, bytes(rng.randrange(256) for _ in range(rng.randrange(40))))) for i in range(1, 50)]
    stream = b"".join(frames)
    for _ in range(50):
        dec, out, i = StreamDecoder(), [], 0
        while i < len(stream):
            j = i + rng.randint(1, 17)
            out.extend(dec.feed(stream[i:j]))
            i = j
        assert [CODEC.encode(m) for m in out] == frames


def test_b061_fuzz_stream_decoder_garbage_poisons_cleanly():
    rng = random.Random(6161)
    for _ in range(500):
        dec = StreamDecoder(max_buffer=4096)
        try:
            for _ in range(20):
                list(dec.feed(bytes(rng.randrange(256) for _ in range(rng.randrange(1, 64)))))
        except FrameError:
            with pytest.raises(FrameError):
                list(dec.feed(b"SK"))


def test_b061_fuzz_sse_adapter_never_raises():
    rng = random.Random(1)
    alphabet = "data:event:id: {}\"kind\":5,\n\r:x\x00\u00e9"
    ad = SSEMessageAdapter()
    for _ in range(2000):
        list(ad.feed("".join(rng.choice(alphabet) for _ in range(rng.randrange(40)))))
    out = list(ad.feed('\n\ndata: {"kind": 5, "channel": 2, "seq": 9, "payload": "s"}\n\n'))
    assert out[-1] == Message(MessageKind.SNAPSHOT, b"s", 2, 9)


def _session_contract(a, b):
    sa, sb = Session(a), Session(b)
    sa.send(MessageKind.HELLO, b"hi")
    sa.send(MessageKind.INPUT, b"in", channel=1)
    got = []
    for _ in range(200):
        got += sb.poll()
        if len(got) == 2:
            break
    assert [m.kind for m in got] == [MessageKind.HELLO, MessageKind.INPUT]
    assert sb.remote_seq == 2
    sb.send(MessageKind.ACK)
    for _ in range(200):
        if sa.poll():
            break
    assert sa.remote_seq == 1


def test_b061_session_contract_over_in_memory_transport():
    _session_contract(*InMemoryTransport.pair())


def test_b061_session_contract_over_udp_loopback():
    a, b = UdpLoopbackTransport(), UdpLoopbackTransport()
    a.connect(b.address)
    b.connect(a.address)
    try:
        _session_contract(a, b)
    finally:
        a.close()
        b.close()


def test_b061_session_contract_over_tcp_loopback():
    a, b = TcpLoopbackTransport.pair()
    try:
        _session_contract(a, b)
    finally:
        a.close()
        b.close()


def test_b061_session_drops_malformed_duplicate_and_stale():
    a, b = InMemoryTransport.pair()
    sb = Session(b)
    a.send(b"garbage")
    f2 = CODEC.encode(Message(MessageKind.SNAPSHOT, b"", seq=2))
    a.send(f2)
    a.send(f2)
    a.send(CODEC.encode(Message(MessageKind.SNAPSHOT, b"", seq=1)))
    assert len(sb.poll()) == 1
    assert sb.stats["malformed"] == 1 and sb.stats["duplicate"] == 1 and sb.stats["stale"] == 1


def test_b061_udp_loopback_refuses_non_loopback():
    t = UdpLoopbackTransport()
    try:
        with pytest.raises(ValueError):
            t.connect(("10.0.0.1", 9))
    finally:
        t.close()
