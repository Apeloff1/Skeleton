"""Durable bounded local import orchestration. No network, automatic target
discovery, credential storage, or inference of permission from a capture.

The operator explicitly admits a manifest and finite execution deadline.
A pulse settles one job using the canonical lead graph and exact page receipts.
A crashed running job is never stolen: an offline drain acknowledgement is
required to resume the same identity. Execution expiry never renews a grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from core.dragon_owner_shards import _private, _open
from core.dragon_offline_dataset_handoff import qualify_manifest, apply_manifest,_manifest
from core.dragon_dataset_ingest import fingerprint
from core.dragon_hoarder_bulk import owner_key
from core.dragon_mongo_receipt import _read_json
from core.dragon_publisher_export_proof import PublisherExportProof

MAX_JOBS = 4096
MAX_OWNER_JOBS = 128
MAX_EXECUTION = 3600
MAX_JOB_BYTES = 128*1024**2
MAX_JOB_ROWS = 1_000_000
SCHEMA = """
CREATE TABLE IF NOT EXISTS export_jobs(
 owner TEXT NOT NULL,id TEXT NOT NULL,manifest TEXT NOT NULL,manifest_sha TEXT NOT NULL,
 proof_json TEXT NOT NULL,expires_at INTEGER NOT NULL,created INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('queued','running','sealed','held','expired')),
 token TEXT,receipt TEXT,PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS export_job_queue ON export_jobs(owner,state,created,id);
"""


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _scope(scope):
    if (not isinstance(scope,dict) or set(scope)!={"tenant_id","owner_id"}
            or any(not isinstance(x,str) or not 1<=len(x)<=256 or x.strip()!=x for x in scope.values())):
        raise ValueError("explicit local owner scope required")
    return owner_key(scope)


def _proof_fields(proof):
    if proof is None:return {}
    if not isinstance(proof,PublisherExportProof):raise ValueError("invalid publisher proof")
    return {"public_key_hex":proof.public_key_hex,"expected_key_sha256":proof.expected_key_sha256,
            "signature_hex":proof.signature_hex}


def _bound_manifest(path,expected_sha,proof):
    _,items,_=_manifest(path,expected_sha=expected_sha,publisher_proof=proof)
    if sum(fingerprint(local)[2] for _,local in items)>MAX_JOB_BYTES:
        raise ValueError("automated import byte bound; use explicit manual import")


class ExportJobs:
    def __init__(self,path,*,create=False):
        self.path=Path(path)
        if create and not self.path.exists():
            _private(self.path,create=True)
            with _open(self.path) as db:db.executescript(SCHEMA)
        _private(self.path)
        with _open(self.path) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_jobs'").fetchone():
                raise ValueError("explicit export job ledger initialization required")

    def enqueue(self,scope,manifest,*,expected_sha,execution_seconds,rights_acknowledged,proof=None):
        owner=_scope(scope)
        if rights_acknowledged is not True or type(execution_seconds) is not int or not 60<=execution_seconds<=MAX_EXECUTION:
            raise ValueError("finite local execution grant required")
        path=Path(manifest)
        # No raw paths or body content from captured web sources enter a job.
        fields=_proof_fields(proof)
        _bound_manifest(path,expected_sha,proof)
        _,report=qualify_manifest(path,expected_manifest_sha=expected_sha,publisher_proof=proof)
        if sum(entry["rows"] for entry in report["entries"])>MAX_JOB_ROWS:
            raise ValueError("automated import row bound; use explicit manual import")
        identifier=_digest([owner,str(path),expected_sha,fields])
        now=int(time.time())
        with _open(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT id,state,expires_at FROM export_jobs WHERE owner=? AND id=?",(owner,identifier)).fetchone()
            if row:
                db.execute("COMMIT")
                return {**dict(row),"replayed":True,"network_executed":False}
            if db.execute("SELECT COUNT(*) FROM export_jobs").fetchone()[0]>=MAX_JOBS or db.execute(
                "SELECT COUNT(*) FROM export_jobs WHERE owner=?",(owner,)).fetchone()[0]>=MAX_OWNER_JOBS:
                raise ValueError("local export job ledger capacity")
            db.execute("INSERT INTO export_jobs VALUES(?,?,?,?,?,?,?,'queued',NULL,NULL)",
                       (owner,identifier,str(path),expected_sha,json.dumps(fields,sort_keys=True),now+execution_seconds,now))
            db.execute("COMMIT")
        return {"id":identifier,"state":"queued","expires_at":now+execution_seconds,
                "entries":len(report["entries"]),"replayed":False,"network_executed":False}

    def pulse(self,scope,*,graph_factory,cancelled=None):
        owner=_scope(scope);token=uuid4().hex
        with _open(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            now=int(time.time())
            db.execute("UPDATE export_jobs SET state='expired' WHERE owner=? AND state='queued' AND expires_at<=?",(owner,now))
            # One active runner per owner, including interrupted running jobs.
            if db.execute("SELECT 1 FROM export_jobs WHERE owner=? AND state='running'",(owner,)).fetchone():
                db.execute("COMMIT")
                return {"state":"drain_required","network_executed":False}
            row=db.execute("SELECT * FROM export_jobs WHERE owner=? AND state='queued' ORDER BY created,id LIMIT 1",(owner,)).fetchone()
            if row is None:
                db.execute("COMMIT")
                return {"state":"idle","network_executed":False}
            job=dict(row)
            db.execute("UPDATE export_jobs SET state='running',token=? WHERE owner=? AND id=? AND state='queued'",(token,owner,job["id"]))
            db.execute("COMMIT")

        def authorize():
            if cancelled is not None and cancelled():raise PermissionError("import runner cancelled")
            with _open(self.path) as db:
                if not db.execute("SELECT 1 FROM export_jobs WHERE owner=? AND id=? AND state='running' AND token=? AND expires_at>?",
                                  (owner,job["id"],token,int(time.time()))).fetchone():
                    raise PermissionError("import execution grant unavailable")

        try:
            authorize()
            saved=json.loads(job["proof_json"])
            proof=PublisherExportProof(**saved) if saved else None
            _bound_manifest(Path(job["manifest"]),job["manifest_sha"],proof)
            authorize()
            report=apply_manifest(Path(job["manifest"]),expected_manifest_sha=job["manifest_sha"],
                scope=scope,graph_factory=graph_factory,rights_acknowledged=True,publisher_proof=proof,authorize=authorize)
            authorize()
            receipt=json.dumps({"manifest_sha256":report["manifest_sha256"],
                    "settlements":report["settlements"],"atomic_batch":False},sort_keys=True)
            state="sealed"
        except Exception as exc:
            # Partial canonical settlements may already exist. Do not erase or
            # claim rollback; replay uses exact source/page identities.
            receipt=json.dumps({"error_class":type(exc).__name__,"partial_settlement_possible":True})
            state="held"
        with _open(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("UPDATE export_jobs SET state=?,token=NULL,receipt=? WHERE owner=? AND id=? AND token=? AND state='running'",
                               (state,receipt,owner,job["id"],token)).rowcount
            if changed!=1:raise PermissionError("job settlement fence changed")
            db.execute("COMMIT")
        return {"id":job["id"],"state":state,"receipt":json.loads(receipt),"network_executed":False}

    def resume(self,scope,identifier,*,offline_drained_acknowledged=False):
        owner=_scope(scope)
        if offline_drained_acknowledged is not True:raise ValueError("stop and drain local worker first")
        with _open(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute("UPDATE export_jobs SET state='queued',token=NULL,receipt=NULL WHERE owner=? AND id=? AND state IN ('held','running') AND expires_at>?",
                               (owner,identifier,int(time.time()))).rowcount
            if changed!=1:raise ValueError("exact unexpired held job required")
            db.execute("COMMIT")
        return {"id":identifier,"state":"queued","deadline_renewed":False}


async def scheduler_pulse():
    """One explicitly enabled owner-local lane, never a remote credential."""
    import asyncio
    import threading
    from core.dragon_corpus_runtime import _bounded,_path
    from core.dragon_lead_graph import LeadGraph
    from core.dragon_raw_export_custody import RawExportCustody
    if os.getenv("SKL_DRAGON_DELIVERY_SCHEDULER","").strip()!="1":
        return {"configured":False,"network_executed":False}
    scope_path=os.getenv("SKL_DRAGON_DELIVERY_SCOPE_JSON","").strip()
    job_path=os.getenv("SKL_DRAGON_EXPORT_JOB_DB_PATH","").strip()
    raw_path=os.getenv("SKL_DRAGON_RAW_EXPORT_DB_PATH","").strip()
    if not scope_path or not (job_path or raw_path):
        return {"configured":True,"failed":True,"reason":"explicit_local_delivery_configuration_required"}
    cancelled=threading.Event()
    def work():
        scope=_read_json(Path(scope_path));_scope(scope)
        answer={"configured":True,"network_executed":False}
        if raw_path and not cancelled.is_set():
            try:answer["retention"]=RawExportCustody(Path(raw_path)).purge_expired(scope,limit=4)
            except (OSError,ValueError,RuntimeError,sqlite3.Error):
                answer["retention"]={"failed":True,"reason":"raw_retention_held"}
        if job_path and not cancelled.is_set():
            try:answer["import"]=ExportJobs(Path(job_path)).pulse(scope,
                 graph_factory=lambda:LeadGraph(_path(scope=scope,create=False)),cancelled=cancelled.is_set)
            except (OSError,ValueError,RuntimeError,sqlite3.Error):
                answer["import"]={"failed":True,"reason":"local_import_held"}
        return answer
    try:
        return await asyncio.wait_for(_bounded(work),timeout=45)
    except (TimeoutError,OSError,ValueError,RuntimeError,sqlite3.Error):
        return {"configured":True,"failed":True,"reason":"bounded_delivery_held","network_executed":False}
    finally:
        # _bounded retains the shared thread credit until physical exit.
        # A timed-out runner may finish its current atomic page; no new page
        # may start after its next authorize check.
        cancelled.set()


def main(argv=None):
    from core.dragon_corpus_runtime import _path
    from core.dragon_lead_graph import LeadGraph
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ledger",required=True,type=Path)
    p.add_argument("--scope-json",required=True,type=Path)
    p.add_argument("--initialize",action="store_true")
    sub=p.add_subparsers(dest="command",required=True)
    admit=sub.add_parser("enqueue")
    admit.add_argument("--manifest",required=True,type=Path)
    admit.add_argument("--manifest-sha256",required=True)
    admit.add_argument("--execution-seconds",type=int,default=900)
    admit.add_argument("--acknowledge-metadata-rights",action="store_true")
    admit.add_argument("--proof-json",type=Path)
    sub.add_parser("pulse")
    resume=sub.add_parser("resume")
    resume.add_argument("--job",required=True)
    resume.add_argument("--offline-drained",action="store_true")
    args=p.parse_args(argv)
    scope=_read_json(args.scope_json.expanduser().absolute())
    _scope(scope)
    jobs=ExportJobs(args.ledger.expanduser().absolute(),create=args.initialize)
    if args.command=="enqueue":
        proof=PublisherExportProof(**_read_json(args.proof_json.expanduser().absolute())) if args.proof_json else None
        result=jobs.enqueue(scope,args.manifest.expanduser().absolute(),expected_sha=args.manifest_sha256,
                            execution_seconds=args.execution_seconds,rights_acknowledged=args.acknowledge_metadata_rights,proof=proof)
    elif args.command=="pulse":
        result=jobs.pulse(scope,graph_factory=lambda:LeadGraph(_path(scope=scope,create=False)))
    else:result=jobs.resume(scope,args.job,offline_drained_acknowledged=args.offline_drained)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":raise SystemExit(main())
