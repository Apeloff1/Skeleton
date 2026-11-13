"""Test-only service-token minting CLI.

    python -m skeleton.gate_plane.s2s.mint_cli mint --service forge-worker \
        --audience gate --scope forge:read --kid test-k1
    python -m skeleton.gate_plane.s2s.mint_cli verify --audience gate --kid test-k1 TOKEN
    python -m skeleton.gate_plane.s2s.mint_cli keyset --kid test-k1

Keys are derived from a fixed, public, **test-only** master so the CLI can
never mint with real material: kids must start with ``test-`` and there is
no option to supply a secret. Never use these tokens outside tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.keyset import export_keyset
from skeleton.gate_plane.s2s.rotation import derived_secret_factory
from skeleton.gate_plane.s2s.tokens import TokenError, TokenSigner, TokenVerifier

TEST_ONLY_MASTER = b"skeleton-s2s-TEST-ONLY-master-not-a-secret-0001"
TEST_KID_PREFIX = "test-"


class CliError(SystemExit):
    pass


def build_test_keyring(kids: Sequence[str], *, clock: Optional[ManualClock] = None) -> KeyRing:
    """Ring with the given test kids; the last one is ACTIVE, earlier ones RETIRING."""
    for kid in kids:
        if not kid.startswith(TEST_KID_PREFIX):
            raise ValueError(f"kid {kid!r} must start with {TEST_KID_PREFIX!r} (test keys only)")
    ring = KeyRing(clock=clock)
    factory = derived_secret_factory(TEST_ONLY_MASTER)
    for kid in kids:
        ring.add_key(kid, factory(kid))
        ring.activate(kid, overlap_s=300.0)
    return ring


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="s2s-mint", description="Mint TEST-ONLY s2s service tokens")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mint")
    m.add_argument("--service", required=True)
    m.add_argument("--audience", required=True)
    m.add_argument("--scope", action="append", default=[])
    m.add_argument("--kid", default="test-k1")
    m.add_argument("--ttl", type=float, default=300.0)
    m.add_argument("--now", type=float, default=None, help="fixed wall clock (unix seconds)")
    m.add_argument("--jti", default=None)
    m.add_argument("--cnf", default=None, help="pin a client-cert SHA-256 fingerprint")
    v = sub.add_parser("verify")
    v.add_argument("--audience", required=True)
    v.add_argument("--kid", default="test-k1")
    v.add_argument("--now", type=float, default=None)
    v.add_argument("token")
    k = sub.add_parser("keyset")
    k.add_argument("--kid", action="append", default=[])
    return p


def main(argv: Optional[List[str]] = None, *, out=None) -> int:
    out = out if out is not None else sys.stdout
    args = _parser().parse_args(argv)
    clock = ManualClock(args.now) if getattr(args, "now", None) is not None else ManualClock()
    try:
        if args.cmd == "mint":
            ring = build_test_keyring([args.kid], clock=clock)
            signer = TokenSigner(
                args.service, ring, clock=clock,
                jti_factory=(lambda: args.jti) if args.jti else None,
            )
            extra = {"cnf": args.cnf} if args.cnf else None
            out.write(signer.mint(args.audience, args.scope, ttl_s=args.ttl, extra=extra) + "\n")
            return 0
        if args.cmd == "verify":
            ring = build_test_keyring([args.kid], clock=clock)
            vt = TokenVerifier(args.audience, ring, clock=clock).verify(args.token)
            out.write(json.dumps({"kid": vt.kid, "claims": vt.claims.to_wire()}, sort_keys=True) + "\n")
            return 0
        ring = build_test_keyring(args.kid or ["test-k1"], clock=clock)
        out.write(json.dumps(export_keyset(ring, issuer="test"), sort_keys=True) + "\n")
        return 0
    except (ValueError, TokenError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
