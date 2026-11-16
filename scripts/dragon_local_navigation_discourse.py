"""Run an owner-approved navigation packet through the real local Jeeves app.

Input: JSON packet OR authenticated crawler packet response on stdin.
Output: local inference receipts and a finite advice envelope on stdout.
This client deliberately cannot reach the remote crawler or dispatch a URL.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
from pathlib import Path
import stat
import sys

from skeleton.ai.webcrawler.navigation_semantics import validate_packet

MAX_PACKET = 32768
MAX_RESPONSE = 128 * 1024


def load_token(path):
    path = Path(path).expanduser()
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 512:
        raise ValueError("private local token file required")
    if os.name == "posix" and (before.st_uid != os.getuid() or before.st_mode & 0o077):
        raise ValueError("local token must be owner-only")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        current = os.fstat(fd)
        if (before.st_dev,before.st_ino,before.st_size)!=(current.st_dev,current.st_ino,current.st_size):
            raise ValueError("local token identity changed")
        token = os.read(fd, 513).decode("ascii").strip()
    finally:
        os.close(fd)
    if not 32 <= len(token) <= 256 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in token):
        raise ValueError("invalid local token")
    return token


def request_discourse(port, token, packet):
    ids = set(validate_packet(packet))
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid loopback port")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=920)
    try:
        data = json.dumps({"packet":packet,"approved":True},ensure_ascii=True).encode()
        connection.request("POST","/v1/dragon/navigation-discourse",body=data,
                           headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        response=connection.getresponse()
        body=response.read(MAX_RESPONSE+1)
        if response.status!=200 or len(body)>MAX_RESPONSE:
            raise RuntimeError("local model discourse did not return a bounded successful result")
        result=json.loads(body)
        advice=result["advice"]
        if (result["network_authorized"] is not False or result["single_local_model_two_roles"] is not True
                or advice["snapshot_digest"]!=packet["snapshot_digest"]
                or advice["packet_digest"]!=packet["packet_digest"] or advice["as_of"]!=packet["as_of"]):
            raise ValueError("local discourse result identity mismatch")
        for key in ("jeeves_rank","dragon_rank"):
            rank=advice[key]
            if not isinstance(rank,list) or not rank or len(rank)!=len(set(rank)) or not set(rank)<=ids:
                raise ValueError("local discourse returned an unknown target")
        receipts=result["role_receipts"]
        if (result.get("candidate_count")!=len(ids) or not isinstance(receipts,list)
                or not 2<=len(receipts)<=18 or len(receipts)%2
                or [r["role"] for r in receipts]!=["jeeves","dragon"]*(len(receipts)//2)
                or receipts[-1].get("stage")!="final"):
            raise ValueError("local role execution receipts missing")
        for offset in range(0,len(receipts),2):
            a,b=receipts[offset:offset+2]
            if (a.get("stage")!=b.get("stage") or a.get("group_digest")!=b.get("group_digest")
                    or a["session_id"]==b["session_id"]):
                raise ValueError("local role match custody mismatch")
        for row in receipts:
            for key in ("group_digest","execution_receipt_digest","output_digest"):
                if not re.fullmatch(r"[a-f0-9]{64}",row.get(key,"")):
                    raise ValueError("local execution digest missing")
        return result
    finally:
        connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True,type=int)
    parser.add_argument("--token-file",required=True)
    parser.add_argument("--approve-local-inference",action="store_true")
    args=parser.parse_args(argv)
    if not args.approve_local_inference:
        parser.error("explicit local inference approval required")
    raw=sys.stdin.buffer.read(MAX_PACKET+1)
    if len(raw)>MAX_PACKET:
        parser.error("navigation packet exceeds input limit")
    try:
        value=json.loads(raw)
        packet=value.get("packet",value)
        receipt=request_discourse(args.port,load_token(args.token_file),packet)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,http.client.HTTPException):
        print("Local navigation discourse not confirmed; refresh packet and model status.",file=sys.stderr)
        return 1
    print(json.dumps(receipt,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
