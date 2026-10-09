"""Pinned census. Projection is not in the payload."""

from __future__ import annotations

import hashlib

PAYLOAD = "organ:3329408|masterplan:15302600|x10:153003200|x100_shard:7650009|eight:100800072|prose:0|clip:1.1"
PIN = "dbe1aeb64225c7802e1b92ad61b24e19d8508b549be27dd2aa051f96157b51ee"


def pin() -> str:
    digest = hashlib.sha256(PAYLOAD.encode()).hexdigest()
    if digest != PIN:
        raise RuntimeError("pin drift")
    return digest


if __name__ == "__main__":
    print(pin())
