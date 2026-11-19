"""Inspect operator-pinned GGUF files, with no native model loading."""
import argparse
from dataclasses import asdict
import json
import sys

from skeleton.native.gguf_preflight import inspect_gguf
from skeleton.app.recovered_evidence import seal, canonical, integer, EvidenceError


def qualify_source(path, *, expected_sha256, max_bytes, authorized):
    if authorized is not True:
        raise PermissionError("explicit model source operator required")
    integer(max_bytes,24,128*1024**3)
    header=inspect_gguf(path,expected_sha256=expected_sha256,max_bytes=max_bytes)
    return seal({"schema":"skeleton.gguf-source-preflight.v1","header":asdict(header),
                 "exact_source_sha_verified":True,"header_only_semantic_validation":True,
                 "full_tensor_validation":False,"tokenizer_verified":False,
                 "license_approved":False,"native_model_loaded":False,
                 "native_model_tested":False,"release_certified":False})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model",required=True)
    parser.add_argument("--expected-sha256",required=True)
    parser.add_argument("--max-bytes",type=int,default=128*1024**3)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        result=qualify_source(args.model,expected_sha256=args.expected_sha256,
                              max_bytes=args.max_bytes,authorized=args.trusted_local_operator)
        print(canonical(result).decode("ascii"))
        return 0
    except (ValueError,PermissionError,OSError,TypeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
