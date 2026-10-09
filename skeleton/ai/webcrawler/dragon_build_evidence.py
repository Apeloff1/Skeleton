"""Authenticated owner-bound, append-only native build provenance receipts.

A binary file is not evidence of successful compilation merely because it has
a console extension. The trusted worker passes actual bytes, toolchain
identity and a private signing key. We verify binary format/ROM checksum and
bind evidence to an immutable source digest + practice attempt. The receipt
chain is HMAC-protected. No endpoint signs caller-supplied verdicts; no XP.
This does not prove a particular compiler ran unless the signing worker is
isolated and verifies its own tool invocation provenance.
"""
from __future__ import annotations
from dataclasses import asdict,dataclass
from hashlib import sha256
import hmac,json,sqlite3
from .dragon_native_practice import DragonNativePracticeLab
from .dragon_native_compile import _verify
from .dragon_practice_lab import _owner,_time

ROM_EXTENSIONS={"game_boy":"gb","game_boy_color":"gbc","nes":"nes"}
MAX_ROM_BYTES=2_000_000

@dataclass(frozen=True)
class BuildReceipt:
    owner:str
    attempt_id:str
    target:str
    source_digest:str
    binary_sha256:str
    bytes_written:int
    toolchain:str
    event_time:float
    chain_index:int
    previous_digest:str
    receipt_digest:str
    signature:str
    claim:str="rom_header_and_content_verified_not_gameplay_verified"
    schema:str="skeleton.ai.dragon.native_build_receipt.v1"

class DragonBuildEvidence:
    def __init__(self,db:sqlite3.Connection,lab:DragonNativePracticeLab,
                 *,private_signing_key:bytes):
        if lab.db is not db:raise ValueError("build evidence must share owner ledger")
        if not isinstance(private_signing_key,bytes) or len(private_signing_key)<32:
            raise ValueError("operator must configure a 256-bit evidence signing key")
        self.db=db;self.lab=lab;self.key=private_signing_key
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_native_build_evidence(
            owner TEXT NOT NULL,attempt_id TEXT NOT NULL,chain_index INTEGER NOT NULL,
            receipt_json TEXT NOT NULL,PRIMARY KEY(owner,chain_index),
            UNIQUE(owner,attempt_id,chain_index))""")
        db.commit()

    def _base(self,owner,attempt):
        _owner(owner)
        row=self.db.execute("""SELECT source_digest,target_id FROM dragon_native_game_attempts
            WHERE owner=? AND attempt_id=?""",(owner,attempt)).fetchone()
        if row is None:raise LookupError("native game attempt not found")
        return row

    @staticmethod
    def _canon(v:object)->bytes:
        return json.dumps(v,sort_keys=True,separators=(",",":"),
                          ensure_ascii=True,allow_nan=False).encode()

    def _signature(self,data:dict)->str:
        return hmac.new(self.key,self._canon(data),sha256).hexdigest()

    def history(self,owner:str,*,authorized:bool)->tuple[BuildReceipt,...]:
        _owner(owner)
        if not authorized:raise PermissionError("native build evidence requires authority")
        rows=self.db.execute("""SELECT receipt_json FROM dragon_native_build_evidence
            WHERE owner=? ORDER BY chain_index""",(owner,)).fetchall()
        previous="0"*64
        result=[]
        for position,(raw,) in enumerate(rows,1):
            record=json.loads(raw)
            signature=record.pop("signature")
            receipt_digest=record.pop("receipt_digest")
            if record.get("owner")!=owner or record.get("chain_index")!=position or (
                record.get("previous_digest")!=previous):
                raise ValueError("native build evidence chain order tampered")
            if not hmac.compare_digest(self._signature(record),signature):
                raise ValueError("native build evidence signature invalid")
            actual=sha256(self._canon(record)).hexdigest()
            if not hmac.compare_digest(actual,receipt_digest):
                raise ValueError("native build evidence digest mismatch")
            record["signature"]=signature;record["receipt_digest"]=receipt_digest
            result.append(BuildReceipt(**record))
            previous=receipt_digest
        return tuple(result)

    def attest_rom(self,owner:str,attempt_id:str,rom:bytes,*,authorized:bool,
                   trusted_worker:bool,toolchain:str,now:float)->BuildReceipt:
        _owner(owner);_time(now)
        if not authorized or not trusted_worker:
            raise PermissionError("native ROM attestations require a trusted compiler worker")
        if not isinstance(rom,bytes) or not 32768<=len(rom)<=MAX_ROM_BYTES:
            raise ValueError("native ROM payload size invalid")
        if toolchain not in ("RGBDS","cc65"):
            raise ValueError("unrecognized trusted native compiler")
        # Check owner and native source before committing any signed claims.
        source_digest,target_id=self._base(owner,attempt_id)
        project=self.lab.project(owner,attempt_id,authorized=True)
        if project.get("digest")!=source_digest:
            raise ValueError("native build source custody mismatch")
        expected_toolchain="RGBDS" if target_id in ("game_boy","game_boy_color") else "cc65"
        if target_id not in ROM_EXTENSIONS or toolchain!=expected_toolchain:
            raise ValueError("native target is not supported for ROM verification")
        if not _verify(target_id,rom):
            raise ValueError("ROM header, size or checksum invalid")
        # Explicitly preserve the issuer's source digest, not caller-provided
        # arbitrary source strings or user-controlled project names.
        history=self.history(owner,authorized=True)
        binary_sha=sha256(rom).hexdigest()
        for item in history:
            if item.attempt_id==attempt_id and item.binary_sha256==binary_sha:
                return item # exact duplicate is a no-op, never farms XP/events
        previous=history[-1].receipt_digest if history else "0"*64
        evidence={
            "schema":"skeleton.ai.dragon.native_build_receipt.v1",
            "owner":owner,"attempt_id":attempt_id,"target":target_id,
            "source_digest":source_digest,"binary_sha256":binary_sha,
            "bytes_written":len(rom),"toolchain":toolchain,"event_time":now,
            "chain_index":len(history)+1,"previous_digest":previous,
            "claim":"rom_header_and_content_verified_not_gameplay_verified",
        }
        receipt_digest=sha256(self._canon(evidence)).hexdigest()
        signature=self._signature(evidence)
        record=BuildReceipt(**evidence,receipt_digest=receipt_digest,
                            signature=signature)
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            # Same-connection owner event chain; fail closed on stale changes.
            tail=self.db.execute("""SELECT receipt_json FROM dragon_native_build_evidence
                WHERE owner=? ORDER BY chain_index DESC LIMIT 1""",(owner,)).fetchone()
            actual=json.loads(tail[0])["receipt_digest"] if tail else "0"*64
            if actual!=previous:raise ValueError("native build chain changed; retry")
            self.db.execute("""INSERT INTO dragon_native_build_evidence(
                owner,attempt_id,chain_index,receipt_json) VALUES(?,?,?,?)""",
                (owner,attempt_id,record.chain_index,
                 self._canon(asdict(record)).decode()))
        return record

    def attest_from_local_file(self,owner:str,attempt_id:str,path,*,authorized:bool,
                               trusted_worker:bool,toolchain:str,now:float)->BuildReceipt:
        from pathlib import Path
        source=Path(path)
        if not source.is_file() or source.is_symlink() or source.stat().st_size>MAX_ROM_BYTES:
            raise ValueError("native compiled artifact must be a regular bounded local file")
        return self.attest_rom(owner,attempt_id,source.read_bytes(),
                               authorized=authorized,trusted_worker=trusted_worker,
                               toolchain=toolchain,now=now)
