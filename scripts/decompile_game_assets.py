#!/usr/bin/env python3
"""Operator-controlled lawful game disassembly and asset-quality evidence CLI.

Use only on owned/open-source/expressly licensed material under current rights.
No copyrighted source, archive files or decompiled code are auto-uploaded or
trained into the production model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from skeleton.jeeves.game_decompilation import (
    MAX_GAME_BYTES, GameDecompilationGrant, decompile_authorized_game,
    SCOPE_STRUCTURE, SCOPE_CODE, SCOPE_ASSETS, SCOPE_PREVIEWS, SCOPE_QUALITY,
    SCOPE_SHADOW, prepare_reviewed_training_candidate,
)

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _regular_source(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(str(path), flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_GAME_BYTES:
            raise ValueError("Game content must be a regular bounded local file")
        with os.fdopen(os.dup(fd), "rb") as source:
            data = source.read(MAX_GAME_BYTES + 1)
        if len(data) != info.st_size:
            raise ValueError("Game content size changed during admission")
        second = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
            second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns
        ):
            raise ValueError("Source file changed during analysis admission")
        return data
    finally:
        os.close(fd)


def _safe_output(dest: Path, report: dict, previews: tuple[tuple[str, bytes], ...], candidate: dict | None = None) -> None:
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("Never overwrite an existing decompilation evidence directory")
    # New, private directory: no relative/symlink child path can be passed
    # because artifact names are fixed by the analyzer and revalidated below.
    parent = dest.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("Evidence destination parent does not exist")
    dest.mkdir(mode=0o700)
    dirfd = os.open(str(dest), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        items = [("report.json", json.dumps(report,sort_keys=True,indent=2,
                     ensure_ascii=True,allow_nan=False).encode())]
        if candidate is not None:
            items.append(("shadow_training_candidate.json",
                          json.dumps(candidate,sort_keys=True,indent=2,
                                     allow_nan=False).encode()))
        for name, data in previews:
            if (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) is None
                or not name.endswith(".png")):
                raise ValueError("Untrusted preview output path rejected")
            items.append((name, data))
        for name, data in items:
            fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os,"O_NOFOLLOW",0), 0o600, dir_fd=dirfd)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                # fdopen manages descriptor once constructed.
                raise
    finally:
        os.close(dirfd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Locally authorized cartridge/project/binary")
    parser.add_argument("--output", type=Path, required=True, help="New private output folder (must not exist)")
    parser.add_argument("--principal", required=True, help="Accountable rights holder reference")
    parser.add_argument("--rights-digest", required=True, help="SHA-256 of external rights evidence")
    parser.add_argument("--attest-rights", action="store_true",
                        help="Explicitly attest game analysis rights; not a license verifier")
    parser.add_argument("--skip-code", action="store_true")
    parser.add_argument("--skip-assets", action="store_true")
    parser.add_argument("--skip-quality", action="store_true")
    parser.add_argument("--export-previews", action="store_true",
                        help="Separate explicit authorization to export reconstructed tile PNGs")
    parser.add_argument("--instruction-limit", type=int, default=2048)
    parser.add_argument("--human-score", type=int, help="Human review score 0–100, opt-in shadow label only")
    parser.add_argument("--reviewer", help="Human reviewer reference, required with score")
    parser.add_argument("--label-evidence-digest", help="SHA-256 of independent human review evidence")
    parser.add_argument("--candidate-tile", action="append", default=[],
                        help="Explicit candidate offset:length:codec (max four; never guessed)")
    args = parser.parse_args(argv)
    if not args.attest_rights:
        parser.error("Source reverse-engineering and training-feature rights must be explicitly attested")
    if not _SHA.fullmatch(args.rights_digest):
        parser.error("--rights-digest must be a lowercase SHA-256")
    if args.human_score is not None and (
        args.skip_quality or not args.reviewer or not args.label_evidence_digest
        or not _SHA.fullmatch(args.label_evidence_digest)
        or not 0 <= args.human_score <= 100
    ):
        parser.error("Shadow labels require quality brief, score 0–100, reviewer and independent label evidence SHA")
    if len(args.candidate_tile)>4:
        parser.error("At most four explicitly scoped candidate regions allowed")
    candidates=[]
    for raw in args.candidate_tile:
        try:
            off,size,codec=raw.split(":")
            candidates.append({"offset":int(off,0),"length":int(size,0),"codec":codec})
        except (ValueError,TypeError) as exc:
            parser.error("Candidate tile format is offset:length:codec")
    data = _regular_source(args.source)
    scopes = [SCOPE_STRUCTURE]
    if not args.skip_code:
        scopes.append(SCOPE_CODE)
    if not args.skip_assets:
        scopes.append(SCOPE_ASSETS)
    if args.export_previews:
        scopes.append(SCOPE_PREVIEWS)
    if not args.skip_quality:
        scopes.append(SCOPE_QUALITY)
    if args.human_score is not None:
        scopes.append(SCOPE_SHADOW)
    grant = GameDecompilationGrant(
        source_sha256=hashlib.sha256(data).hexdigest(),
        rights_evidence_digest=args.rights_digest,
        principal_ref=args.principal, approved_scopes=tuple(scopes),
        rights_acknowledged=True,
    )
    # Local operator acknowledgement, NOT cryptographic/license verification.
    def local_explicit_authority(scope: str, bound: GameDecompilationGrant) -> bool:
        return scope in scopes and bound is grant and args.attest_rights
    result=decompile_authorized_game(
        data,args.source.name,grant=grant,authorize=local_explicit_authority,
        inspect_code=not args.skip_code,inspect_assets=not args.skip_assets,
        export_previews=args.export_previews,derive_quality=not args.skip_quality,
        candidate_tile_regions=candidates,instruction_limit=args.instruction_limit,
    )
    candidate = None
    if args.human_score is not None:
        candidate = prepare_reviewed_training_candidate(
            result,grant=grant,authorize=local_explicit_authority,
            human_score=args.human_score,reviewer_ref=args.reviewer,
            label_evidence_digest=args.label_evidence_digest,
        )
        # Human label is a separate explicit result, never hidden in
        # the original game evidence digest or inserted into model weights.
    _safe_output(args.output,result.report,result.previews,candidate=candidate)
    print(json.dumps({
        "report_sha256":result.report["report_sha256"],
        "source_sha256":result.report["source_sha256"],
        "format":result.report["format"],
        "preview_files_created":len(result.previews),
        "output":str(args.output),
        "production_model_training_performed":False,
        "external_license_verification_performed":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
