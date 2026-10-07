"""Shamir secret sharing over GF(257) — vault sealing without a single key.

The vault's master seal is the most dangerous byte string in the system:
whoever holds it holds everything. The correct number of copies of a master
secret is *zero* — so we never store one. Instead the seal is split into
**N shares such that any K reconstruct it, and K−1 reveal nothing**
(Shamir 1979, information-theoretically secure, not merely computationally).

Implementation notes
--------------------
- Arithmetic runs in GF(257), the smallest prime field that fits a byte.
  The one byte value that collides with the field prime (256) is rejected
  at split time by salting the secret with a random nonce byte; the nonce
  rides along in each share, so reconstruction is unaffected.
- Polynomial coefficients are drawn from ``secrets.SystemRandom`` — OS
  entropy, never ``random.random``.
- Shares are self-describing: ``(index, nonce, value)`` triples. Losing a
  share loses nothing about the secret; finding one share reveals nothing.
- No dependencies. The whole scheme is ~100 lines because Shamir's scheme
  is genuinely that small — the security lives in the field, not the code.

Usage::

    shares = ShamirSeal.split(secret_bytes, n=5, k=3)
    # distribute shares to five custodians; any three can unseal:
    secret = ShamirSeal.combine(shares[:3])
"""

from __future__ import annotations

import secrets as _secrets
from dataclasses import dataclass
from typing import List, Tuple

from skeleton.kernel.errors import VaultError

_FIELD_PRIME = 257  # GF(257): the smallest prime field containing a byte


class SealingError(VaultError):
    code = "VLT.SEALING"


@dataclass(frozen=True)
class Share:
    """One share of a sealed secret. Self-describing and portable."""
    index: int       # x-coordinate, 1..n (never 0 — that's the secret)
    nonce: int       # salt byte that shifted the secret off 256
    values: Tuple[int, ...]  # y-coordinates, one per secret byte

    def to_dict(self) -> dict:
        return {"index": self.index, "nonce": self.nonce, "values": list(self.values)}

    @classmethod
    def from_dict(cls, d: dict) -> "Share":
        return cls(index=d["index"], nonce=d["nonce"], values=tuple(d["values"]))


# ---------------------------------------------------------------------------
# GF(257) arithmetic
# ---------------------------------------------------------------------------

def _add(a: int, b: int) -> int:
    return (a + b) % _FIELD_PRIME


def _sub(a: int, b: int) -> int:
    return (a - b) % _FIELD_PRIME


def _mul(a: int, b: int) -> int:
    return (a * b) % _FIELD_PRIME


def _inv(a: int) -> int:
    if a == 0:
        raise SealingError("division by zero in GF(257)")
    # Fermat's little theorem: a^(p-2) ≡ a^(-1) (mod p)
    return pow(a, _FIELD_PRIME - 2, _FIELD_PRIME)


def _eval_poly(coeffs: List[int], x: int) -> int:
    """Horner's method in GF(257)."""
    acc = 0
    for c in reversed(coeffs):
        acc = _add(_mul(acc, x), c)
    return acc


class ShamirSeal:
    """Split and combine master secrets via (k, n) threshold sharing."""

    @staticmethod
    def split(secret: bytes, n: int, k: int) -> List[Share]:
        """
        Split ``secret`` into ``n`` shares; any ``k`` reconstruct it.

        The secret is salted with one random nonce byte; every byte value
        v becomes (v + nonce) mod 257, which keeps all values strictly
        inside GF(257) — byte 256 would otherwise alias the field prime.
        """
        if not (1 < k <= n <= 255):
            raise SealingError(
                "invalid threshold parameters",
                context={"n": n, "k": k},
            )
        if not secret:
            raise SealingError("cannot seal an empty secret")

        rng = _secrets.SystemRandom()
        nonce = rng.randrange(1, _FIELD_PRIME)
        salted = [(b + nonce) % _FIELD_PRIME for b in secret]

        # One random (k-1)-degree polynomial per secret byte;
        # coefficient[0] is the salted secret byte itself.
        polys: List[List[int]] = [
            [v] + [rng.randrange(_FIELD_PRIME) for _ in range(k - 1)]
            for v in salted
        ]

        shares: List[Share] = []
        for x in range(1, n + 1):
            ys = tuple(_eval_poly(poly, x) for poly in polys)
            shares.append(Share(index=x, nonce=nonce, values=ys))
        return shares

    @staticmethod
    def combine(shares: List[Share]) -> bytes:
        """
        Reconstruct the secret from any ``k`` distinct shares.

        Lagrange interpolation at x=0 recovers each polynomial's constant
        term (the salted byte); subtracting the share nonce unsalts it.
        """
        if not shares:
            raise SealingError("no shares provided")
        nonces = {s.nonce for s in shares}
        if len(nonces) != 1:
            raise SealingError("shares come from different sealings")
        indices = [s.index for s in shares]
        if len(set(indices)) != len(indices):
            raise SealingError("duplicate share indices")
        length = len(shares[0].values)
        if any(len(s.values) != length for s in shares):
            raise SealingError("share length mismatch")

        nonce = shares[0].nonce
        secret = bytearray()
        for byte_i in range(length):
            # Lagrange basis at x=0 for this byte's shares
            acc = 0
            for j, sj in enumerate(shares):
                num, den = 1, 1
                for m, sm in enumerate(shares):
                    if m == j:
                        continue
                    num = _mul(num, -sm.index)
                    den = _mul(den, _sub(sj.index, sm.index))
                acc = _add(acc, _mul(sj.values[byte_i], _mul(num, _inv(den))))
            secret.append(_sub(acc, nonce) % 256)
        return bytes(secret)
