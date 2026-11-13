"""Explicit trusted-operator signing of original local AI source receipts.

This command is not an LLM tool. Signing declares operator approval and a
traceable source-rights receipt digest; it is not a legal license audit.
Output is created exclusively, mode 0600, with directory fsync.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import time

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError,loads,refuse,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    sign_manifest_for_operator,verify_signed_manifest,ingest_authorized_sources,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli import (
    _environment_key,_read_private_manifest,
)

_NAME=re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z",re.ASCII)


def _publish_private(output,raw):
    if not isinstance(output, Path) or not output.is_absolute():
        refuse("source approval output must be absolute")
    if type(output.name) is not str or _NAME.fullmatch(output.name) is None:
        refuse("output must have a safe basename")
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import open_private_root
    from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError
    try:
        directory=open_private_root(output.parent)
    except (OSError,ValueError,SpineError) as exc:
        raise CognitionError("trusted manifest output directory cannot be safely anchored") from exc
    created=False
    try:
        st=os.fstat(directory)
        if (not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid()
            or st.st_mode&0o022):
            refuse("manifest output directory must be private and operator owned")
        try:
            fd=os.open(output.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                       os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
            created=True
        except OSError as exc:
            raise CognitionError("manifest output exists or cannot be safely created") from exc
        try:
            index=0
            while index<len(raw):
                advanced=os.write(fd,raw[index:])
                if advanced<=0:refuse("short operator manifest write")
                index+=advanced
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
    except BaseException:
        if created:
            os.unlink(output.name,dir_fd=directory)
        raise
    finally:
        os.close(directory)


def main(argv=None):
    parser=argparse.ArgumentParser(description="Explicit source-manifest HMAC custody")
    parser.add_argument("--record",required=True,type=Path,
        help="Unsigned closed JSON record, private regular file")
    parser.add_argument("--source-root",required=True,type=Path)
    parser.add_argument("--signed-out",required=True,type=Path)
    parser.add_argument("--approve-source-rights",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.approve_source_rights:
            refuse("explicit operator rights approval required")
        key=_environment_key()
        raw=_read_private_manifest(args.record)
        record=loads(raw,maximum=32768)
        signed=sign_manifest_for_operator(record,key)
        checked=verify_signed_manifest(signed,key,observed_at=int(time.time()))
        # Independently re-read source file inodes and exact signed SHA values
        # before publishing any operator authorization.
        index=ingest_authorized_sources(args.source_root,checked,
                    scope=checked.scope,observed_at=int(time.time()))
        _publish_private(args.signed_out,signed)
        print(json.dumps({
            "schema":"offline-source-manifest-operator-signing.v1",
            "status":"signed-source-manifest-created",
            "source_count":len(index.documents),
            "scope_sha256":checked.scope.digest(),
            "signed_record_sha256":checked.signed_record_sha256,
            "independent_model_license_review_proved":False,
            "native_model_executed":False,
            "release_certified":False,
        },sort_keys=True))
        return 0
    except (Exception,KeyboardInterrupt) as exc:
        print(json.dumps({"status":"held","error_class":type(exc).__name__,
                          "native_model_executed":False,
                          "release_certified":False},sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
