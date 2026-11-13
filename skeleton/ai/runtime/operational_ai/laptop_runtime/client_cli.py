"""Minimal scriptable client with stdin prompt and no CLI credential exposure."""
from __future__ import annotations
import argparse
import json
import os
import secrets
import sys
from .client import LaptopClient
from .contracts import ContractViolation,identifier,utf8,identity_hash

class _RedactedArguments(argparse.ArgumentParser):
    """Invalid command options cannot disclose a private user task."""

    def error(self, message: str) -> None:
        raise ContractViolation("invalid local client arguments")


def main(argv=None):
    p=_RedactedArguments(description="Call a private local offline AI listener")
    p.add_argument("--port",type=int,default=8765)
    p.add_argument("--action",choices=("create","turn","replay","history","status"),required=True)
    p.add_argument("--session")
    p.add_argument("--request-id")
    p.add_argument("--stdin-prompt",action="store_true")
    p.add_argument("--expected-model-sha256",
                   help="Independent installed GGUF model digest to pin")
    p.add_argument("--expected-tokenizer-sha256",
                   help="Exact paired tokenizer digest to pin")
    try:
        args=p.parse_args(argv)
        if type(args.port) is not int or not 1 <= args.port <= 65535:
            raise ContractViolation("finite loopback client port required")
        # Exact installed model and tokenizer claims must travel together.
        # Command-line arguments override optional operator environment pins;
        # neither supplies installer-source rights or release qualification.
        model=args.expected_model_sha256
        tokenizer=args.expected_tokenizer_sha256
        if model is None:model=os.environ.get("SKELETON_LOCAL_AI_MODEL_SHA256")
        if tokenizer is None:tokenizer=os.environ.get("SKELETON_LOCAL_AI_TOKENIZER_SHA256")
        if (model is None)!=(tokenizer is None):
            raise ContractViolation("paired native source digests required")
        if model is not None:
            model=identity_hash(model)
            tokenizer=identity_hash(tokenizer)
        secret=os.environ.get("SKELETON_LOCAL_AI_BEARER","")
        client=LaptopClient(port=args.port,bearer=secret,
                            expected_model_sha256=model,
                            expected_tokenizer_sha256=tokenizer)
        if args.action=="create":
            if args.session is not None or args.request_id is not None or args.stdin_prompt:
                raise ContractViolation("unexpected create arguments")
            result=client.create()
        elif args.action=="status":
            if args.session is not None or args.request_id is not None or args.stdin_prompt:
                raise ContractViolation("unexpected status arguments")
            client.identity()
            result=client.request("status",{})
            client.identity()
        elif args.action=="history":
            if not args.session or args.request_id is not None or args.stdin_prompt:
                raise ContractViolation("invalid history arguments")
            result=client.history(identifier(args.session))
        else:
            if not args.session or not args.stdin_prompt:
                raise ContractViolation("turn/replay require session and stdin prompt")
            if args.action=="replay" and not args.request_id:
                raise ContractViolation("replay requires the original request identifier")
            identifier(args.session,"session")
            if args.request_id is not None:
                identifier(args.request_id,"request")
            raw=sys.stdin.buffer.read(32769)
            if len(raw)>32768:raise ContractViolation("prompt byte ceiling")
            # Preserve exact line breaks, indentation and trailing whitespace.
            # Validation rejects empty or whitespace-only input without
            # silently rewriting a code task before durable replay hashing.
            prompt=utf8(raw.decode("utf-8","strict"))
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
