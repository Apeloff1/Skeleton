"""Immutable preregistration and observation ledger for mechanic trials."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,sqlite3,math

from .dragon_mechanic_causal_analysis import MechanicTrial,TrialProtocol


@dataclass(frozen=True)
class TrialAssignment:
    trial_id:str
    intervention:bool
    context_group:str
    source_id:str


@dataclass(frozen=True)
class TrialObservation:
    trial_id:str
    outcome_success:bool
    observed_at:float
    evidence_digest:str


RANDOMIZATION_VERSION="dragon.hash-randomization.v1"

def expected_randomized_intervention(trial_id:str,seed:str)->bool:
    if not isinstance(trial_id,str) or not trial_id:
        raise ValueError("invalid randomized trial id")
    if len(seed)!=64 or any(c not in "0123456789abcdef" for c in seed):
        raise ValueError("invalid randomization seed")
    material=(RANDOMIZATION_VERSION+"\0"+seed+"\0"+trial_id).encode()
    return bool(sha256(material).digest()[0]&1)

def cryptographic_allocation_evidence(assignments:tuple[TrialAssignment,...],seed:str)->str:
    canonical=[]
    for a in assignments:
        expected=expected_randomized_intervention(a.trial_id,seed)
        if a.intervention is not expected:
            raise ValueError("assignment does not match hash-randomization protocol")
        canonical.append((a.trial_id,a.intervention,a.context_group,a.source_id))
    return sha256(json.dumps([RANDOMIZATION_VERSION,seed,sorted(canonical)],
        separators=(",",":")).encode()).hexdigest()


class DragonTrialLedger:
    def __init__(self,db:sqlite3.Connection):
        self.db=db
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_trial_protocols(
          owner TEXT NOT NULL,protocol_id TEXT NOT NULL,hypothesis_id TEXT NOT NULL,
          mechanic TEXT NOT NULL,assignment_digest TEXT NOT NULL,
          outcome_definition TEXT NOT NULL,registered_at REAL NOT NULL,
          PRIMARY KEY(owner,protocol_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_trial_design_evidence(
          owner TEXT NOT NULL,protocol_id TEXT NOT NULL,allocation_method TEXT NOT NULL,
          allocation_evidence_digest TEXT NOT NULL,interference_assessment TEXT NOT NULL,
          interference_evidence_digest TEXT NOT NULL,assessed_at REAL NOT NULL,
          allocation_verified INTEGER NOT NULL DEFAULT 0,
          verification_version TEXT NOT NULL DEFAULT '',
          PRIMARY KEY(owner,protocol_id))""")
        columns={row[1] for row in db.execute("PRAGMA table_info(dragon_trial_design_evidence)")}
        if "allocation_verified" not in columns:
            db.execute("ALTER TABLE dragon_trial_design_evidence ADD COLUMN allocation_verified INTEGER NOT NULL DEFAULT 0")
        if "verification_version" not in columns:
            db.execute("ALTER TABLE dragon_trial_design_evidence ADD COLUMN verification_version TEXT NOT NULL DEFAULT ''")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_trial_assignments(
          owner TEXT NOT NULL,protocol_id TEXT NOT NULL,trial_id TEXT NOT NULL,
          intervention INTEGER NOT NULL,context_group TEXT NOT NULL,source_id TEXT NOT NULL,
          PRIMARY KEY(owner,protocol_id,trial_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS dragon_trial_observations(
          owner TEXT NOT NULL,protocol_id TEXT NOT NULL,trial_id TEXT NOT NULL,
          outcome INTEGER NOT NULL,observed_at REAL NOT NULL,evidence_digest TEXT NOT NULL,
          PRIMARY KEY(owner,protocol_id,trial_id))""");db.commit()

    def preregister(self,owner:str,*,hypothesis_id:str,mechanic:str,
        assignments:tuple[TrialAssignment,...],outcome_definition:str,
        registered_at:float,authorized:bool)->TrialProtocol:
        if not authorized: raise PermissionError("trial preregistration requires authorization")
        if not owner or not hypothesis_id or not mechanic or not outcome_definition:
            raise ValueError("trial protocol fields required")
        if not math.isfinite(registered_at) or registered_at<0 or len(assignments)<2:
            raise ValueError("invalid trial preregistration")
        ids=set()
        for a in assignments:
            if not a.trial_id or a.trial_id in ids or not a.context_group or not a.source_id:
                raise ValueError("invalid or duplicate trial assignment")
            ids.add(a.trial_id)
        canonical=sorted((a.trial_id,a.intervention,a.context_group,a.source_id) for a in assignments)
        assignment_digest=sha256(json.dumps(canonical,separators=(",",":")).encode()).hexdigest()
        protocol_id=sha256(json.dumps([hypothesis_id,mechanic,assignment_digest,
            outcome_definition,registered_at],separators=(",",":")).encode()).hexdigest()
        with self.db:
            self.db.execute("""INSERT INTO dragon_trial_protocols VALUES(?,?,?,?,?,?,?)""",
                (owner,protocol_id,hypothesis_id,mechanic,assignment_digest,
                 outcome_definition,registered_at))
            self.db.executemany("""INSERT INTO dragon_trial_assignments VALUES(?,?,?,?,?,?)""",
                [(owner,protocol_id,a.trial_id,int(a.intervention),a.context_group,a.source_id)
                 for a in assignments])
        return TrialProtocol(protocol_id,assignment_digest,True,False,True,False,False)

    def attest_design(self,owner:str,protocol_id:str,*,allocation_method:str,
        allocation_evidence_digest:str,interference_assessment:str,
        interference_evidence_digest:str,assessed_at:float,authorized:bool,
        randomization_seed:str|None=None)->None:
        if not authorized: raise PermissionError("trial design attestation requires authorization")
        if allocation_method not in {"cryptographic_randomization","external_randomization"}:
            raise ValueError("unverified allocation method")
        if interference_assessment not in {"none_detected","modeled"}:
            raise ValueError("interference assessment required")
        for d in (allocation_evidence_digest,interference_evidence_digest):
            if len(d)!=64 or any(c not in "0123456789abcdef" for c in d): raise ValueError("invalid design evidence digest")
        if not math.isfinite(assessed_at) or assessed_at<0: raise ValueError("invalid design assessment time")
        if not self.db.execute("SELECT 1 FROM dragon_trial_protocols WHERE owner=? AND protocol_id=?",(owner,protocol_id)).fetchone():
            raise KeyError("trial protocol not found")
        allocation_verified=0;verification_version="external.unverified.v1"
        if allocation_method=="cryptographic_randomization":
            rows=self.db.execute("""SELECT trial_id,intervention,context_group,source_id
              FROM dragon_trial_assignments WHERE owner=? AND protocol_id=? ORDER BY trial_id""",
              (owner,protocol_id)).fetchall()
            assignments=tuple(TrialAssignment(x[0],bool(x[1]),x[2],x[3]) for x in rows)
            computed=cryptographic_allocation_evidence(assignments,randomization_seed or "")
            if allocation_evidence_digest!=computed:
                raise ValueError("allocation evidence digest mismatch")
            allocation_verified=1;verification_version=RANDOMIZATION_VERSION
        expected=(allocation_method,allocation_evidence_digest,interference_assessment,
            interference_evidence_digest,assessed_at,allocation_verified,verification_version)
        old=self.db.execute("""SELECT allocation_method,allocation_evidence_digest,
          interference_assessment,interference_evidence_digest,assessed_at,
          allocation_verified,verification_version FROM dragon_trial_design_evidence
          WHERE owner=? AND protocol_id=?""",(owner,protocol_id)).fetchone()
        if old and old!=expected: raise ValueError("immutable trial design evidence conflict")
        with self.db:
            self.db.execute("""INSERT OR IGNORE INTO dragon_trial_design_evidence(
              owner,protocol_id,allocation_method,allocation_evidence_digest,
              interference_assessment,interference_evidence_digest,assessed_at,
              allocation_verified,verification_version) VALUES(?,?,?,?,?,?,?,?,?)""",
              (owner,protocol_id,*expected))

    def observe(self,owner:str,protocol_id:str,observation:TrialObservation,*,
                authorized:bool)->None:
        if not authorized: raise PermissionError("trial observation requires authorization")
        if not math.isfinite(observation.observed_at) or observation.observed_at<0:
            raise ValueError("invalid observation time")
        if len(observation.evidence_digest)!=64 or any(c not in "0123456789abcdef" for c in observation.evidence_digest):
            raise ValueError("invalid observation evidence digest")
        row=self.db.execute("""SELECT registered_at FROM dragon_trial_protocols
          WHERE owner=? AND protocol_id=?""",(owner,protocol_id)).fetchone()
        if not row: raise KeyError("trial protocol not found")
        if observation.observed_at<=row[0]: raise ValueError("outcome must follow preregistration")
        if not self.db.execute("""SELECT 1 FROM dragon_trial_assignments
          WHERE owner=? AND protocol_id=? AND trial_id=?""",
          (owner,protocol_id,observation.trial_id)).fetchone():
            raise ValueError("observation has no preregistered assignment")
        with self.db:
            existing=self.db.execute("""SELECT outcome,observed_at,evidence_digest
              FROM dragon_trial_observations WHERE owner=? AND protocol_id=? AND trial_id=?""",
              (owner,protocol_id,observation.trial_id)).fetchone()
            expected=(int(observation.outcome_success),observation.observed_at,observation.evidence_digest)
            if existing and existing!=expected: raise ValueError("immutable trial observation conflict")
            self.db.execute("""INSERT OR IGNORE INTO dragon_trial_observations VALUES(?,?,?,?,?,?)""",
                (owner,protocol_id,observation.trial_id,*expected))

    def materialize(self,owner:str,protocol_id:str,*,authorized:bool
                    )->tuple[tuple[MechanicTrial,...],TrialProtocol]:
        if not authorized: raise PermissionError("trial materialization requires authorization")
        p=self.db.execute("""SELECT mechanic,assignment_digest FROM dragon_trial_protocols
          WHERE owner=? AND protocol_id=?""",(owner,protocol_id)).fetchone()
        if not p: raise KeyError("trial protocol not found")
        rows=self.db.execute("""SELECT a.trial_id,a.intervention,a.context_group,a.source_id,
          o.outcome FROM dragon_trial_assignments a JOIN dragon_trial_observations o
          ON a.owner=o.owner AND a.protocol_id=o.protocol_id AND a.trial_id=o.trial_id
          WHERE a.owner=? AND a.protocol_id=? ORDER BY a.trial_id""",(owner,protocol_id)).fetchall()
        design=self.db.execute("""SELECT allocation_method,interference_assessment,
          allocation_verified,verification_version FROM dragon_trial_design_evidence
          WHERE owner=? AND protocol_id=?""",(owner,protocol_id)).fetchone()
        allocation_verified=bool(design and design[0]=="cryptographic_randomization"
          and design[2] and design[3]==RANDOMIZATION_VERSION)
        interference_assessed=bool(design and design[1] in ("none_detected","modeled"))
        trials=tuple(MechanicTrial(r[0],p[0],bool(r[1]),bool(r[4]),allocation_verified,r[2],r[3]) for r in rows)
        complete=len(rows)==self.db.execute("""SELECT COUNT(*) FROM dragon_trial_assignments
          WHERE owner=? AND protocol_id=?""",(owner,protocol_id)).fetchone()[0]
        protocol=TrialProtocol(protocol_id,p[1],True,allocation_verified,True,complete,interference_assessed)
        return trials,protocol
