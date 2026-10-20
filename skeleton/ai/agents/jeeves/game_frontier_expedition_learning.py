"""Dragon's bounded and independently verified original-game lesson almanac.

A lesson may be promoted only if two independent source-replay verifiers
attest to the same original game and Dragon's separate adversarial attack
matrix rejects forgery attempts. Promotion means *reviewed knowledge note*,
never trained neural weights. SQLite generations are atomic and CAS guarded.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
from typing import Mapping

from .game_frontier_expedition import ExpeditionError,_digest,_json
from .game_frontier_expedition_dragon import DragonLesson


@dataclass(frozen=True,slots=True)
class LearningEvidence:
    game_digest:str
    dragon_report_receipt:str
    independent_review_receipt:str
    adversarial_attack_receipt:str
    reviewer_ids:tuple[str,str]
    source_approved:bool

    def __post_init__(self):
        for d in (self.game_digest,self.dragon_report_receipt,
                  self.independent_review_receipt,self.adversarial_attack_receipt):
            if type(d) is not str or len(d)!=64 or any(c not in "0123456789abcdef" for c in d):
                raise ExpeditionError("Dragon learning evidence needs exact source receipts")
        if (type(self.reviewer_ids) is not tuple or len(self.reviewer_ids)!=2
                or any(type(v) is not str or not 3<=len(v)<=128 for v in self.reviewer_ids)
                or self.reviewer_ids[0]==self.reviewer_ids[1]):
            raise ExpeditionError("Dragon promotion requires distinct reviewer identities")
        if type(self.source_approved) is not bool:
            raise ExpeditionError("learning source approval must be explicit")


def review_dragon_lesson(lesson:DragonLesson,proof:LearningEvidence,
                         game_report:Mapping,adversarial:Mapping,
                         attacks:Mapping)->dict:
    if not isinstance(lesson,DragonLesson) or not isinstance(proof,LearningEvidence):
        raise ExpeditionError("Dragon lesson promotion needs typed independent evidence")
    if not all(isinstance(v,Mapping) for v in (game_report,adversarial,attacks)):
        raise ExpeditionError("Dragon promotion requires full reviewer evidence")
    def integrity(candidate:Mapping)->bool:
        return candidate.get("receipt_digest")==_digest({
            key:value for key,value in candidate.items() if key!="receipt_digest"
        })
    authored_notes=game_report.get("lessons",())
    valid_lesson=any(
        isinstance(item,Mapping) and
        item.get("game_digest")==lesson.game_digest and
        item.get("topic")==lesson.topic and
        item.get("severity")==lesson.severity and
        item.get("evidence_receipt")==lesson.evidence_receipt and
        item.get("recommendation")==lesson.recommendation
        for item in authored_notes
    )
    if not integrity(game_report) or not integrity(adversarial) or not integrity(attacks):
        raise ExpeditionError("Dragon review root receipt was altered")
    if not valid_lesson:
        raise ExpeditionError("Dragon lesson is not present in reviewed source evidence")
    if (lesson.game_digest!=proof.game_digest
            or proof.dragon_report_receipt!=game_report.get("receipt_digest")
            or proof.independent_review_receipt!=adversarial.get("receipt_digest")
            or proof.adversarial_attack_receipt!=attacks.get("receipt_digest")
            or lesson.game_digest not in [x.get("game_digest") for x in game_report.get("game_evidence",[])]
            or lesson.evidence_receipt not in [x.get("receipt_digest") for x in game_report.get("game_evidence",[])]
            or lesson.game_digest not in adversarial.get("source_games",[])
            or adversarial.get("approved_for_verified_learning_notes") is not True
            or adversarial.get("model_weights_updated") is not False
            or attacks.get("all_attacks_rejected") is not True
            or len(attacks.get("attacks",{}))!=6
            or any(x!="rejected" for x in attacks["attacks"].values())
            or proof.source_approved is not True):
        raise ExpeditionError("Dragon independent training evidence does not authorize lesson")
    payload={
        "schema":"skeleton.dragon.reviewed_lesson.v1",
        "game":proof.game_digest,
        "topic":lesson.topic,"severity":lesson.severity,
        "note":lesson.recommendation,
        "source_receipt":lesson.evidence_receipt,
        "dragon_receipt":proof.dragon_report_receipt,
        "independent_receipt":proof.independent_review_receipt,
        "attack_receipt":proof.adversarial_attack_receipt,
        "reviewers":list(proof.reviewer_ids),
        "knowledge_note_verified":True,
        "model_weights_changed":False,
        "copyright_clearance_inferred":False,
        "native_engine_origin_proven":False,
    }
    payload["receipt_digest"]=_digest(payload)
    return payload


class DragonKnowledgeStore:
    def __init__(self,path:Path):
        if not isinstance(path,Path):
            raise ExpeditionError("Dragon knowledge store needs controlled file path")
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),timeout=15,isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_verified_notes(
                sequence INTEGER PRIMARY KEY,
                prior TEXT NOT NULL,
                receipt TEXT NOT NULL UNIQUE,
                payload BLOB NOT NULL
            )""")
        self.closed=False

    def _load(self)->list[dict]:
        if self.closed:
            raise ExpeditionError("Dragon knowledge archive has been closed")
        rows=self.db.execute(
            "SELECT sequence,prior,receipt,payload FROM dragon_verified_notes ORDER BY sequence"
        ).fetchall()
        previous="0"*64
        out=[]
        for index,(sequence,prior,receipt,raw) in enumerate(rows,1):
            if sequence!=index or prior!=previous or not isinstance(raw,bytes):
                raise ExpeditionError("Dragon archive generation history incomplete")
            if len(raw)>8192 or len(out)>8192:
                raise ExpeditionError("Dragon archived lessons exceeded evidence budget")
            try:
                note=json.loads(raw)
            except ValueError as exc:
                raise ExpeditionError("Dragon archived lesson JSON is corrupted") from exc
            if (not isinstance(note,dict) or _json(note)!=raw
                    or note.get("receipt_digest")!=_digest({
                        k:v for k,v in note.items() if k!="receipt_digest"
                    })):
                raise ExpeditionError("Dragon knowledge note was altered")
            expected=_digest({"sequence":sequence,"prior":previous,"note":note["receipt_digest"]})
            if receipt!=expected:
                raise ExpeditionError("Dragon archived receipt chain was tampered")
            previous=receipt
            out.append({"sequence":sequence,"chain_receipt":receipt,"note":note})
        return out

    def append(self,note:dict,*,expected_head:str="0"*64)->dict:
        if not isinstance(note,dict) or note.get("schema")!="skeleton.dragon.reviewed_lesson.v1" or (
                note.get("knowledge_note_verified") is not True
                or note.get("model_weights_changed") is not False
                or note.get("receipt_digest")!=_digest({
                    k:v for k,v in note.items() if k!="receipt_digest"
                })):
            raise ExpeditionError("unapproved Dragon knowledge cannot enter archive")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current=self._load()
            previous=current[-1]["chain_receipt"] if current else "0"*64
            if expected_head!=previous:
                raise ExpeditionError("Dragon knowledge archive advanced; retry with fresh head")
            if any(x["note"]["receipt_digest"]==note["receipt_digest"] for x in current):
                raise ExpeditionError("Dragon lesson has already been admitted")
            generation=len(current)+1
            receipt=_digest({"sequence":generation,"prior":previous,"note":note["receipt_digest"]})
            self.db.execute(
                "INSERT INTO dragon_verified_notes VALUES(?,?,?,?)",
                (generation,previous,receipt,_json(note)),
            )
            self.db.execute("COMMIT")
            return {"generation":generation,"receipt":receipt,
                    "note_receipt":note["receipt_digest"]}
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def history(self)->tuple[dict,...]:
        return tuple(self._load())

    def close(self):
        if not self.closed:
            self.db.close()
            self.closed=True

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
