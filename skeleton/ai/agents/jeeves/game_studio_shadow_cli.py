"""CLI for self-extending shadow-clone original-game training and audit ledger.

Every per-sim cycle is appended to an exclusive, flushed, hash-chained NDJSON
receipt log *before* the run continues. A completed certificate is only
published after full receipt-chain verification. Interrupted files are
deliberately not certified; operators can inspect incomplete durable logs.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock

from .game_studio_environment import make_studio_source, parse_studio_source
from .game_studio_rule_training_cli import _read_json
from .game_studio_scenario_lab import ANGLES
from .game_studio_shadow_saturation import (
    DRY_CYCLES_REQUIRED, ShadowSaturationError,
    run_shadow_saturation, verify_shadow_receipts,
)

LEDGER_SCHEMA="skeleton.game_builder.shadow_receipt_log.v1"


def _write_exclusive(path:Path, raw:bytes, max_bytes:int) -> str:
    if not 1<=len(raw)<=max_bytes:
        raise ShadowSaturationError("completed receipt file exceeds storage budget")
    target=Path(path).expanduser().absolute()
    if target.is_symlink() or not target.parent.is_dir():
        raise ShadowSaturationError("private existing receipt parent required")
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return sha256(raw).hexdigest()


def execute_shadow_room(
    *,source:dict,output:Path,ledger_path:Path,
    authorized:bool,rights_cleared:bool,
    train_policy:bool=True,
    seed:int=3,steps:int=3,max_cycles_per_sim:int=24,
    max_replay_work_per_sim:int=10000,workers:int=2,
    angles:tuple[str,...]=ANGLES,
) -> dict:
    if authorized is not True or rights_cleared is not True:
        raise PermissionError("game simulation and candidate learning require rights and operator admission")
    source=parse_studio_source(source)
    output=Path(output).expanduser().absolute()
    ledger_path=Path(ledger_path).expanduser().absolute()
    if output==ledger_path:
        raise ShadowSaturationError("final signed results and append-only live logs require separate paths")
    if output.exists() or ledger_path.exists():
        raise FileExistsError("source-bound reports are never silently overwritten")
    if ledger_path.is_symlink() or not ledger_path.parent.is_dir():
        raise ShadowSaturationError("ledger requires existing private storage directory")
    fd=os.open(ledger_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    counter=0
    lock=Lock()
    try:
        with os.fdopen(fd,"wb") as stream:
            def append(receipt):
                nonlocal counter
                with lock:
                    counter+=1
                    row={
                        "schema_version":LEDGER_SCHEMA,
                        "sequence":counter,
                        "angle":receipt["angle"],
                        "cycle":receipt["cycle"],
                        "receipt_digest":receipt["digest"],
                        "receipt":receipt,
                    }
                    raw=(json.dumps(row,sort_keys=True,separators=(",",":"),
                                    allow_nan=False)+"\n").encode()
                    if len(raw)>70000:
                        raise ShadowSaturationError("per-cycle event exceeds bounded log admission")
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            document=run_shadow_saturation(
                source,seed=seed,steps=steps,
                angles=angles,max_cycles_per_sim=max_cycles_per_sim,
                dry_cycles=DRY_CYCLES_REQUIRED,
                max_replay_work_per_sim=max_replay_work_per_sim,
                workers=workers,
                on_receipt=append,
                train_policy=train_policy,
                authorized=authorized,rights_cleared=rights_cleared,
            )
        if verify_shadow_receipts(document,source=source) is not True:
            raise ShadowSaturationError("source-bound shadow report failed receipt-chain verification")
        records=[row for sim in document["simulations"] for row in sim["receipts"]]
        by_digest={row["digest"]:row for row in records}
        observed=[]
        # Independently compare persisted bytes to the actually committed
        # receipt digests. A gap, duplicate or reordered event fails closed.
        with ledger_path.open("rb") as stream:
            for line in stream:
                row=json.loads(line)
                if (set(row)!={"schema_version","sequence","angle",
                               "cycle","receipt_digest","receipt"}
                    or row["schema_version"]!=LEDGER_SCHEMA
                    or row["sequence"]!=len(observed)+1
                    or row["receipt_digest"] not in by_digest
                    or row["receipt"]!=by_digest[row["receipt_digest"]]):
                    raise ShadowSaturationError("persistent shadow ledger differs from real cycle receipts")
                observed.append(row["receipt_digest"])
        if len(observed)!=len(records) or len(set(observed))!=len(records):
            raise ShadowSaturationError("persistent shadow ledger lost or duplicated cycles")
        public={
            "schema_version":"skeleton.game_builder.shadow_training_certificate.v1",
            "laboratory":document,
            "source_digest":sha256(json.dumps(
                source,sort_keys=True,separators=(",",":"),allow_nan=False
            ).encode()).hexdigest(),
            "ledger_sha256":sha256(ledger_path.read_bytes()).hexdigest(),
            "ledger_event_count":len(observed),
            "signed_source_replay":True,
            "candidate_trained":bool(train_policy),
            "saturation_scope":"bounded_semantic_and_policy_gain_only",
            "all_simulations_saturated":document["all_saturated_within_bounds"],
            "outcome_if_not_saturated":"resource_or_cycle_limit_unproven",
            "universal_training_exhaustion_proven":False,
            "automatic_production_promotion":False,
            "production_neural_weights_modified":False,
        }
        raw=json.dumps(public,sort_keys=True,separators=(",",":"),
                       ensure_ascii=True,allow_nan=False).encode()
        digest=_write_exclusive(output,raw,16*1024*1024)
        return {
            "report":str(output),"report_sha256":digest,
            "ledger":str(ledger_path),"ledger_sha256":public["ledger_sha256"],
            "ledger_event_count":len(observed),
            "simulation_count":document["parent_sim_count"],
            "actual_shadow_and_primary_runs":document["total_executed_primary_shadow_runs"],
            "saturated_simulations":document["individual_saturation_verified_count"],
            "all_saturated_within_bounds":document["all_saturated_within_bounds"],
            "candidate_policy_count":document["candidate_q_policy_count"],
            "neural_production_weights_modified":False,
        }
    except BaseException:
        # Preserve the incomplete append-only ledger for forensic review.
        # Never issue a completion certificate for an interrupted operation.
        raise


def verify_shadow_certificate(path:Path,ledger_path:Path,source:dict) -> dict:
    """Offline independent full-engine re-execution and persisted ledger check."""
    canonical=parse_studio_source(source)
    doc=_read_json(Path(path),limit=16*1024*1024)
    if (type(doc) is not dict or doc.get("schema_version")!=
            "skeleton.game_builder.shadow_training_certificate.v1"
            or doc.get("production_neural_weights_modified") is not False
            or doc.get("universal_training_exhaustion_proven") is not False
            or doc.get("automatic_production_promotion") is not False):
        raise ShadowSaturationError("certificate cannot confer unverified production authority")
    expected=sha256(json.dumps(
        canonical,sort_keys=True,separators=(",",":"),allow_nan=False,
    ).encode()).hexdigest()
    if doc["source_digest"]!=expected:
        raise ShadowSaturationError("independent original source differs from certificate")
    if not verify_shadow_receipts(doc["laboratory"],source=canonical):
        raise ShadowSaturationError("saved run cannot be re-executed against original engine")
    ledger=Path(ledger_path)
    if ledger.is_symlink() or not ledger.is_file() or ledger.stat().st_size>16*1024*1024:
        raise ShadowSaturationError("ledger path changed or exceeds forensic capacity")
    data=ledger.read_bytes()
    if sha256(data).hexdigest()!=doc["ledger_sha256"]:
        raise ShadowSaturationError("append-only log content differs from signed certificate")
    available={
        row["digest"]:row
        for sim in doc["laboratory"]["simulations"]
        for row in sim["receipts"]
    }
    count=0
    found=set()
    for line in data.splitlines():
        try:
            row=json.loads(line)
        except (TypeError,ValueError) as exc:
            raise ShadowSaturationError("corrupted append-only scrutiny log") from exc
        count+=1
        if (type(row) is not dict or
                set(row)!={"schema_version","sequence","angle",
                          "cycle","receipt_digest","receipt"} or
                row["schema_version"]!=LEDGER_SCHEMA or
                row["sequence"]!=count or
                row["receipt_digest"] in found or
                row["receipt_digest"] not in available or
                row["receipt"]!=available[row["receipt_digest"]]):
            raise ShadowSaturationError("persisted log event identity or sequence differs")
        found.add(row["receipt_digest"])
    if count!=doc["ledger_event_count"] or count!=len(available):
        raise ShadowSaturationError("lost or duplicated durable scrutiny events")
    return {
        "independently_verified":True,
        "source_engine":canonical["editor"],
        "log_receipts_reexecuted":count,
        "simulations_verified":doc["laboratory"]["parent_sim_count"],
        "saturated_within_bounds":doc["laboratory"]["all_saturated_within_bounds"],
        "universal_exhaustion_proven":False,
        "production_neural_weights_modified":False,
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--engine")
    group.add_argument("--source-file",type=Path)
    parser.add_argument("--settings-json")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ledger",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=3)
    parser.add_argument("--steps",type=int,default=3)
    parser.add_argument("--max-cycles-per-sim",type=int,default=24)
    parser.add_argument("--max-replay-work-per-sim",type=int,default=10000)
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--angles",nargs="+",choices=ANGLES,default=list(ANGLES))
    parser.add_argument("--spectator-only",action="store_true")
    parser.add_argument("--verify-only",action="store_true")
    parser.add_argument("--authorized",action="store_true")
    parser.add_argument("--rights-cleared",action="store_true")
    args=parser.parse_args(argv)
    if args.source_file is not None:
        if args.settings_json:
            parser.error("saved source cannot be silently reconfigured")
        source=_read_json(args.source_file,limit=131072)
    else:
        settings=json.loads(args.settings_json) if args.settings_json else None
        source=make_studio_source(args.engine,settings)
    if args.verify_only:
        result=verify_shadow_certificate(args.output,args.ledger,source)
        print(json.dumps(result,sort_keys=True))
        return 0
    result=execute_shadow_room(
        source=source,output=args.output,ledger_path=args.ledger,
        authorized=args.authorized,rights_cleared=args.rights_cleared,
        train_policy=not args.spectator_only,
        seed=args.seed,steps=args.steps,
        max_cycles_per_sim=args.max_cycles_per_sim,
        max_replay_work_per_sim=args.max_replay_work_per_sim,
        workers=args.workers,angles=tuple(args.angles),
    )
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
