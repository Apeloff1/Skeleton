"""Owner CLI for the optional transformer sentence-embedding memory bank.

All assets and dependencies must already exist locally. The operator is
responsible for verifying the upstream trust, supported format and license.
Never pass a downloaded/unreviewed graph directly to this native runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.app.jeeves_approved_memory import ApprovedMemory,MemoryRejected
from skeleton.app.jeeves_sentence_encoder import EncoderSpec
from skeleton.app.jeeves_transformer_memory import TransformerMemoryIndex

_SHA=re.compile(r"[0-9a-f]{64}\Z")


def _digest(value):
    if type(value) is not str or not _SHA.fullmatch(value):
        raise MemoryRejected("expected exact lowercase SHA-256")
    return value


def _output(value):
    print(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False))


def _spec(args):
    return EncoderSpec.parse({
        "model_path":str(args.model_file.absolute()),
        "model_sha256":_digest(args.model_sha256),
        "tokenizer_path":str(args.tokenizer_file.absolute()),
        "tokenizer_sha256":_digest(args.tokenizer_sha256),
        "output_name":args.output_name,"dimensions":args.dimensions,
        "max_length":args.max_length,"pooling":args.pooling,"threads":args.threads,
        "query_prefix":args.query_prefix,"document_prefix":args.document_prefix,
    })


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("install","status","refresh","remove","search"):
        p=sub.add_parser(name)
        p.add_argument("--database",type=Path,required=True)
        p.add_argument("--model-digest",required=True)
        p.add_argument("--tokenizer-digest",required=True)
        if name=="install":
            p.add_argument("--model-file",type=Path,required=True)
            p.add_argument("--model-sha256",required=True)
            p.add_argument("--tokenizer-file",type=Path,required=True)
            p.add_argument("--tokenizer-sha256",required=True)
            p.add_argument("--output-name",default="last_hidden_state")
            p.add_argument("--dimensions",type=int,required=True)
            p.add_argument("--max-length",type=int,default=256)
            p.add_argument("--pooling",choices=("mean","cls","sentence"),default="mean")
            p.add_argument("--threads",type=int,default=2)
            p.add_argument("--query-prefix",default="")
            p.add_argument("--document-prefix",default="")
            p.add_argument("--expected-prior")
        if name in ("install","refresh","remove"):
            p.add_argument("--approve",action="store_true")
        if name in ("refresh","remove"):
            p.add_argument("--encoder-identity",required=True)
        if name=="refresh":
            p.add_argument("--cursor")
            p.add_argument("--limit",type=int,default=16)
        if name=="search":
            p.add_argument("--query",required=True)
            p.add_argument("--limit",type=int,default=8)
            p.add_argument("--kind",action="append")
            p.add_argument("--include-private-text",action="store_true",
                           help="Explicitly print the matched private notes to the terminal.")
    args=parser.parse_args(argv)
    try:
        if not args.database.is_file():
            raise MemoryRejected("existing canonical database required")
        model=_digest(args.model_digest); tokenizer=_digest(args.tokenizer_digest)
        if args.command in ("install","refresh","remove") and not args.approve:
            raise MemoryRejected("explicit --approve is required")
        with OfflineChatStore(args.database) as store:
            index=TransformerMemoryIndex(ApprovedMemory(store,model,tokenizer))
            try:
                if args.command=="install":
                    value=index.install(_spec(args),approved=True,expected_prior=args.expected_prior)
                elif args.command=="status":
                    value=index.status()
                elif args.command=="refresh":
                    value=index.refresh(expected_encoder=_digest(args.encoder_identity),approved=True,
                                        cursor=args.cursor,limit=args.limit)
                elif args.command=="remove":
                    value=index.uninstall(_digest(args.encoder_identity),approved=True)
                else:
                    value=index.search(args.query,limit=args.limit,kinds=args.kind)
                    if not args.include_private_text:
                        value["records"]=[{key:r[key] for key in ("memory_id","revision","sha256",
                                            "kind","cosine","encoder_identity")} for r in value["records"]]
                    value["private_text_included"]=args.include_private_text
                _output(value)
            finally:
                index.close()
        return 0
    except (MemoryRejected,RuntimeContractError,OSError,ValueError,sqlite3.Error,OverflowError):
        print("Transformer memory operation held: local asset, dependency, approval, scope or storage failed.",
              file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
