"""Minimal scriptable client with stdin prompt and no CLI credential exposure."""
from __future__ import annotations
import argparse
import json
import os
import secrets
import sys
from .client import LaptopClient
from .contracts import ContractViolation,identifier,utf8

def main(argv=None):
    p=argparse.ArgumentParser(description="Call a private local offline AI listener")
    p.add_argument("--port",type=int,default=8765)
    p.add_argument("--action",choices=("create","turn","replay","history","status"),required=True)
    p.add_argument("--session")
    p.add_argument("--request-id")
    p.add_argument("--stdin-prompt",action="store_true")
    args=p.parse_args(argv)
    try:
        secret=os.environ.get("SKELETON_LOCAL_AI_BEARER","")
        client=LaptopClient(port=args.port,bearer=secret)
        if args.action=="create":
            if args.session or args.request_id or args.stdin_prompt:
                raise ContractViolation("unexpected create arguments")
            result=client.create()
        elif args.action=="status":
            if args.session or args.request_id or args.stdin_prompt:
                raise ContractViolation("unexpected status arguments")
            result=client.request("status",{})
        elif args.action=="history":
            if not args.session or args.request_id or args.stdin_prompt:
                raise ContractViolation("invalid history arguments")
            result=client.history(identifier(args.session))
        else:
            if not args.session or not args.stdin_prompt:
                raise ContractViolation("turn/replay require session and stdin prompt")
            raw=sys.stdin.buffer.read(32769)
            if len(raw)>32768:raise ContractViolation("prompt byte ceiling")
            prompt=utf8(raw.decode("utf-8","strict").strip())
            request=args.request_id
            if args.action=="turn":
                request=request or "r_"+secrets.token_hex(16)
                result=client.turn(identifier(args.session),identifier(request),prompt)
            else:
                if not request:raise ContractViolation("replay needs original request ID")
                result=client.replay(identifier(args.session),identifier(request),prompt)
        print(json.dumps({"status":"ok","result":result},sort_keys=True,ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),
              file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
