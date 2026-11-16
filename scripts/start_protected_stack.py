#!/usr/bin/env python3
"""Explicit signed co-hosted backend and guarded native engine launch.

Requires independently reviewed writer cutover and launch plan, actual local
model assets, external mTLS reviewer, and a private persistent state directory.
No Mongo migration, automatic model download, or inference qualification.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"backend")]

from scripts.start_protected_backend import _approval,_file,_reserve_cutover,_source
from skeleton.app.protected_stack import (
    ProtectedStackLaunchPlan,VerifiedProtectedStackLaunch,ProtectedStackDenied,
    assert_local_configuration,create_launch_reviewer,run_cohosted_stack,
)


async def _run(launch,witness,args):
    reviewer=create_launch_reviewer(launch,ca_path=args.reviewer_ca,
                            client_cert_path=args.reviewer_client_cert,
                            client_key_path=args.reviewer_client_key)
    try:
        assert_local_configuration(launch,os.environ)
        from backend.server import app
        from skeleton.api.server import create_app,get_state
        from core.canonical_memory import _engine_client
        # Verify the globally constructed backend transport rather than
        # relying solely on mutable environment values.
        if (_engine_client is None or
                _engine_client.config.base_url!=f"http://127.0.0.1:{launch.plan.engine_port}"):
            raise ProtectedStackDenied("actual backend engine transport differs from signed port")
        _source(launch.plan.source_head)
        await run_cohosted_stack(launch,reviewer,backend_app=app,engine_factory=create_app,
                                engine_state=get_state,checkpoint=witness.record)
    finally:
        await reviewer.aclose()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-head",required=True)
    parser.add_argument("--plan",required=True,type=Path,help="signed canonical writer cutover JSON")
    parser.add_argument("--signature",required=True,type=Path)
    parser.add_argument("--authority",required=True)
    parser.add_argument("--deployment",required=True)
    parser.add_argument("--operator-public-key-hex",required=True)
    parser.add_argument("--launch-plan",required=True,type=Path)
    parser.add_argument("--launch-signature",required=True,type=Path)
    parser.add_argument("--state-dir",required=True,type=Path)
    parser.add_argument("--reviewer-ca",required=True,type=Path)
    parser.add_argument("--reviewer-client-cert",required=True,type=Path)
    parser.add_argument("--reviewer-client-key",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if os.name!="posix" or re.fullmatch(r"[0-9a-f]{64}",args.operator_public_key_hex) is None:
            raise ProtectedStackDenied("trusted POSIX deployment and public key required")
        writer=_approval(args)
        plan=ProtectedStackLaunchPlan.parse(_file(args.launch_plan,64*1024))
        launch=VerifiedProtectedStackLaunch(plan,writer,_file(args.launch_signature,64),
                                            bytes.fromhex(args.operator_public_key_hex))
        assert_local_configuration(launch,os.environ)
        _source(plan.source_head)
        with _reserve_cutover(writer,args.state_dir) as witness:
            asyncio.run(_run(launch,witness,args))
        # The shared reservation stays ACTIVE after shutdown. Retirement is
        # an independently signed offline operation, never automatic here.
        print("Protected stack drained; deployment retirement remains operator-held.")
        return 0
    except (Exception,KeyboardInterrupt):
        print("Protected co-hosted launch denied or shutdown uncertain; no readiness grant.",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
