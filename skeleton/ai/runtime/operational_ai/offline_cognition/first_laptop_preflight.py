"""Read-only first-laptop source, private-root and installed-GGUF preflight.

This is a real host/source check with no model generation and no database
mutation. Even success cannot qualify a Windows/WSL2 device, native weights,
rights clearance, cancellation, cold restart, security or release.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from .core.contracts import (
    CognitionError, integer, sha, fingerprint, refuse,
)
from .grounded_cli import _environment_key, _read_private_manifest
from .manifest_custody import verify_signed_manifest, ingest_authorized_sources
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.path_policy import (
    open_private_root,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError

MAX_FREE_BYTES=2**53-1
MAX_REQUIRED_FREE=2**40


def _absolute_root(raw, *, label):
    # Path() returns the platform-specific PosixPath/WindowsPath subclass;
    # rejecting those would reject every ordinary pathlib caller. Continue
    # to enforce absolute, no-traversal and descriptor-anchored custody below.
    if type(raw) is not str and not isinstance(raw, Path):
        refuse("trusted absolute "+label+" path required")
    path=Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        refuse("non-absolute or traversing "+label+" root")
    return path


def inspect_private_root(raw, *, label, required_free_bytes=0):
    """Anchor all ancestors, then measure actual filesystem free blocks."""
    path=_absolute_root(raw,label=label)
    integer(required_free_bytes,maximum=MAX_REQUIRED_FREE)
    try:
        fd=open_private_root(path)
    except (OSError,ValueError,SpineError) as exc:
        raise CognitionError("private "+label+" root not safely accessible") from exc
    try:
        stat=os.fstat(fd)
        free=os.fstatvfs(fd)
        available=min(MAX_FREE_BYTES,free.f_bavail*free.f_frsize)
        if available<required_free_bytes:
            refuse("private "+label+" filesystem headroom below operator threshold")
        if stat.st_nlink<1:
            refuse("private "+label+" directory unlinked")
        return {
            "root_type":label,
            "descriptor_anchored":True,
            "symlink_ancestors_rejected":True,
            "operator_private_root_verified":True,
            "available_bytes_observed":available,
            "threshold_bytes":required_free_bytes,
            "writable_probe_performed":False,
            "state_db_integrity_checked":False,
        }
    finally:
        os.close(fd)


def observed_host():
    """Observe the Linux kernel without claiming an approved WSL2 installation."""
    if os.name!="posix" or not hasattr(os,"uname"):
        refuse("POSIX/Linux filesystem custody required")
    system=os.uname().sysname
    if system!="Linux":
        refuse("only Linux kernel/WSL2 Linux environment supported")
    return {
        "linux_kernel_observed":True,
        "linux_or_wsl2":True,
        "wsl2_version_independently_attested":False,
        "clean_windows_11_host_qualified":False,
        "native_cancel_or_gpu_pressure_qualified":False,
    }


def inspect_first_laptop(*,model_root,source_root,source_manifest,state_dir,
                         queue_dir,tenant,subject,operator_key,observed_at,
                         context=2048,max_output_tokens=128,threads=4,
                         minimum_free_bytes=1_073_741_824):
    """No side effects: verify signed source bytes and actual installed-model receipt."""
    host=observed_host()
    integer(observed_at,minimum=1)
    integer(context,minimum=128,maximum=131072)
    integer(max_output_tokens,minimum=1,maximum=8192)
    integer(threads,minimum=1,maximum=64)
    if max_output_tokens>=context:
        refuse("native output cannot exhaust reserved context")
    integer(minimum_free_bytes,minimum=1,maximum=MAX_REQUIRED_FREE)
    if type(tenant) is not str or type(subject) is not str:
        refuse("typed original model principal required")
    model_path=_absolute_root(model_root,label="installed-model")
    source_path=_absolute_root(source_root,label="original-sources")
    manifest_path=Path(source_manifest)
    if not manifest_path.is_absolute() or ".." in manifest_path.parts:
        refuse("absolute signed manifest required")
    signed=_read_private_manifest(manifest_path)
    manifest=verify_signed_manifest(signed,operator_key,observed_at=observed_at)
    if (tenant,subject)!=(manifest.scope.tenant,manifest.scope.subject):
        refuse("operator command principal not bound to signed source manifest")
    # Explicitly walk each private SQLite/source path component before IO.
    roots=(
        inspect_private_root(source_path,label="original-sources",required_free_bytes=0),
        inspect_private_root(state_dir,label="native-spine",required_free_bytes=minimum_free_bytes),
        inspect_private_root(queue_dir,label="signed-work-queue",required_free_bytes=minimum_free_bytes),
    )
    index=ingest_authorized_sources(source_path,manifest,
                                    scope=manifest.scope,observed_at=observed_at)
    from skeleton.ai.runtime.operational_ai.laptop_runtime.installation import source_receipt
    installed=source_receipt(model_path,
                            expected_model_sha256=manifest.scope.model_sha256,
                            require_rights=True)
    if not installed.content_verified or not installed.rights_approved:
        refuse("original installed GGUF archive/rights receipt not validated")
    if installed.model_sha256!=manifest.scope.model_sha256:
        refuse("installed model SHA differs from exact signed source scope")
    if not installed.archive_sha256 or not installed.source_sha:
        refuse("source-bound installed model archive receipt missing")
    rows=[{
        "source_id":k,
        "source_sha256":document.source.sha256,
        "original_bytes":len(document.payload),
    } for k,document in sorted(index.documents.items())]
    source_digest=fingerprint(rows)
    return {
        "schema":"offline-first-laptop-source-preflight.v1",
        "status":"preflight-source-verified-release-held",
        "scope_sha256":manifest.scope.digest(),
        "installed_model_sha256":sha(installed.model_sha256),
        "signed_tokenizer_sha256":sha(manifest.scope.tokenizer_sha256),
        "source_receipt_sha256":source_digest,
        "source_count":len(rows),
        "source_bytes_total":sum(r["original_bytes"] for r in rows),
        "source_manifest_hmac_verified":True,
        "original_source_bytes_verified":True,
        "installer_content_receipt_verified":True,
        "installer_rights_approval_flag_observed":True,
        "private_root_observations":roots,
        "host":host,
        "context_requested":context,
        "max_output_tokens_requested":max_output_tokens,
        "threads_requested":threads,
        "real_native_model_loaded":False,
        "native_tokenizer_activated_and_checked":False,
        "native_output_observed":False,
        "signed_work_order_created":False,
        "second_replay_observed":False,
        "model_legal_rights_independently_proved":False,
        "real_windows_device_qualified":False,
        "release_certified":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only signed-source laptop preflight")
    parser.add_argument("--model-root",type=Path,required=True)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--source-manifest",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--queue-dir",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--context",type=int,default=2048)
    parser.add_argument("--max-new-tokens",type=int,default=128)
    parser.add_argument("--threads",type=int,default=4)
    parser.add_argument("--minimum-free-bytes",type=int,default=1_073_741_824)
    args=parser.parse_args(argv)
    try:
        result=inspect_first_laptop(
            model_root=args.model_root,
            source_root=args.source_root,
            source_manifest=args.source_manifest,
            state_dir=args.state_dir,
            queue_dir=args.queue_dir,
            tenant=args.tenant,
            subject=args.subject,
            operator_key=_environment_key(),
            observed_at=int(time.time()),
            context=args.context,
            max_output_tokens=args.max_new_tokens,
            threads=args.threads,
            minimum_free_bytes=args.minimum_free_bytes,
        )
        print(json.dumps(result,sort_keys=True))
        return 0
    except (Exception,KeyboardInterrupt) as exc:
        # No source bytes, path, output, key material or prompt in diagnostics.
        print(json.dumps({"schema":"offline-first-laptop-source-preflight.v1",
            "status":"held","error_class":type(exc).__name__,
            "native_model_activated":False,"release_certified":False},
            sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
