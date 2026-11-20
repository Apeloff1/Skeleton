"""User-rated local answer quality and source-bound conversational refinement.

The only quality authority is an actual reviewed turn and the user's explicit
feedback. Diagnostics are deterministic hints; neither a rating nor a shape
check certifies correctness or automatically changes model weights.
"""
from __future__ import annotations

from collections import Counter
import json
import re
import time
from typing import Any

from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.jeeves_approved_memory import (
    MemoryRejected, MemoryConflict, _digest, _stable, _text,
)
from skeleton.app.offline_grounding import audit_answer_faithfulness

SCHEMA = "skeleton.jeeves.turn-feedback.v1"
REVIEW_SCHEMA = "skeleton.jeeves.turn-review.v1"
MAX_NOTE_BYTES = 768
MAX_REVIEW_BYTES = 262144
MAX_FLAGS = 8
MAX_AGGREGATE = 100
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_FLAGS = {
    "incorrect": "Identify questionable factual claims and distinguish uncertainty from established evidence.",
    "missed_instruction": "Recheck every explicit requirement of the original request.",
    "incomplete": "Identify omitted deliverables, unresolved steps and missing edge cases.",
    "irrelevant": "Focus on the actual question; remove unrelated material.",
    "too_verbose": "Remove duplication and unnecessary detail while preserving essential content.",
    "too_brief": "Fill material explanatory or implementation gaps with concrete details.",
    "poor_reasoning": "Re-examine assumptions, alternatives, counterexamples and consistency.",
    "format": "Correct the requested output structure without changing well-supported content.",
    "tone": "Match the audience and requested conversational style.",
    "grounding": "Separate supplied evidence from unsupported assertions; do not invent citations.",
    "stale_context": "Honor the latest explicit correction and distinguish old context from current facts.",
    "unverified_actions": "Distinguish work actually performed from plans, suggestions and unverified claims.",
}
_RATINGS = frozenset({"helpful","needs_improvement","mixed"})


def _sha(value: Any) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise MemoryRejected("invalid feedback digest")
    return value


def _id(value: Any) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise MemoryRejected("invalid feedback conversation identity")
    return value


def _positive(value: Any) -> int:
    if type(value) is not int or not 1<=value<2**53:
        raise MemoryRejected("invalid feedback revision")
    return value


def _flags(value: Any) -> list[str]:
    if (type(value) is not list or len(value)>MAX_FLAGS
            or any(type(x) is not str or x not in _FLAGS for x in value)
            or len(set(value))!=len(value)):
        raise MemoryRejected("invalid feedback flag selection")
    return sorted(value)


def _note(value: Any) -> str:
    if value=="":
        return ""
    return _text(value,MAX_NOTE_BYTES)


def _target_shape(pin: Any) -> dict:
    expected={"turn_revision","question_sha256","raw_answer_sha256","visible_answer_sha256"}
    if type(pin) is not dict or set(pin)!=expected:
        raise MemoryRejected("invalid reviewed turn pin")
    return {"turn_revision":_positive(pin["turn_revision"]),
            "question_sha256":_sha(pin["question_sha256"]),
            "raw_answer_sha256":_sha(pin["raw_answer_sha256"]),
            "visible_answer_sha256":_sha(pin["visible_answer_sha256"])}


def _json_shape(text: str) -> bool:
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:
                raise ValueError("duplicate keys")
            result[key]=value
        return result
    def reject(_):
        raise ValueError("nonfinite JSON")
    try:
        return isinstance(json.loads(text,object_pairs_hook=pairs,parse_constant=reject),(dict,list))
    except (ValueError,RecursionError):
        return False


def inspect_shape(question: str, answer: str) -> dict:
    """A deliberately limited nonsemantic diagnostic layer.

    It never assigns a global quality score. Literal matches and formatting
    checks can produce false positives and do not establish factual accuracy.
    """
    question=_text(question,262144)
    if type(answer) is not str or len(answer.encode("utf-8"))>MAX_REVIEW_BYTES:
        return {"findings":[],"bounded_review":False,"semantic_quality_certified":False}
    findings=[]
    words=len(answer.split())
    # Only narrow explicit English forms; an arbitrary mention of JSON or
    # words is not a constraint. Natural language paraphrases require review.
    cap=re.search(r"\b(?:at most|no more than|maximum of)\s+([1-9][0-9]{0,4})\s+words\b",question,re.I)
    if cap and words>int(cap.group(1)):
        findings.append({"id":"word-budget","flag":"too_verbose",
                         "observed":words,"requested":int(cap.group(1)),
                         "method":"explicit-English-word-cap"})
    if re.search(r"\b(?:return|reply with|output)\s+(?:valid\s+)?JSON\s+only\b",question,re.I):
        if not _json_shape(answer):
            findings.append({"id":"json-shape","flag":"format","method":"strict-JSON-parse"})
    fence=None
    for line in answer.splitlines():
        match=re.fullmatch(r"\s{0,3}(\x60{3,}|~{3,})([^\n]*)",line)
        if match is None:
            continue
        marker=match.group(1)
        if fence is None:
            fence=(marker[0],len(marker))
        elif marker[0]==fence[0] and len(marker)>=fence[1] and not match.group(2).strip():
            fence=None
    if fence:
        findings.append({"id":"unclosed-fence","flag":"format","method":"fenced-code-boundary"})
    repeated=Counter(line.strip().casefold() for line in answer.splitlines()
                     if len(line.strip())>=40)
    repeats=sum(n-1 for n in repeated.values() if n>=3)
    if repeats>=2:
        findings.append({"id":"repeated-long-lines","flag":"too_verbose",
                         "observed":repeats,"method":"exact-normalized-line-repetition"})
    # Formatting and repetition hints are not proofs of bad answers: for
    # example a quoted passage or deliberately repetitive poem may be valid.
    if re.search(r"\b(?:I (?:have )?(?:uploaded|emailed|deployed|merged|released)|"
                 r"successfully (?:uploaded|merged|deployed|released))\b",answer,re.I):
        findings.append({"id":"action-claim-cue","flag":"unverified_actions",
                         "method":"lexical-action-claim-cue"})
    return {"findings":findings,"bounded_review":True,"word_count":words,
            "byte_count":len(answer.encode("utf-8")),"semantic_quality_certified":False,
            "human_review_required":True}


class TurnFeedback:
    def __init__(self,store: OfflineChatStore,model_digest: str,tokenizer_digest: str):
        if not isinstance(store,OfflineChatStore):
            raise MemoryRejected("canonical local chat store required")
        self.store=store
        self.scope=(_sha(model_digest),_sha(tokenizer_digest))
        with store._transaction():
            store._db.execute("""CREATE TABLE IF NOT EXISTS jeeves_turn_feedback (
                session_id TEXT NOT NULL, request_id TEXT NOT NULL,
                model_digest TEXT NOT NULL, tokenizer_digest TEXT NOT NULL,
                turn_revision INTEGER NOT NULL, version INTEGER NOT NULL CHECK(version>=1),
                target_json TEXT NOT NULL, rating TEXT NOT NULL, flags_json TEXT NOT NULL,
                note TEXT NOT NULL, updated_at INTEGER NOT NULL, content_sha256 TEXT NOT NULL,
                PRIMARY KEY(session_id,request_id),
                FOREIGN KEY(session_id,request_id) REFERENCES offline_turns(session_id,request_id)
                    ON DELETE CASCADE
            )""")
            store._db.execute("""CREATE INDEX IF NOT EXISTS jeeves_feedback_scope
                ON jeeves_turn_feedback(model_digest,tokenizer_digest,updated_at)""")

    def _resolve(self,sid: str,revision: int) -> tuple[dict,str,str,int,str,str|None]:
        sid=_id(sid);revision=_positive(revision)
        stored=self.store.load(sid,*self.scope)
        if revision>stored.revision:
            raise MemoryConflict("reviewed turn not available")
        messages=stored.transcript.to_list()
        count=1 if messages and messages[0]["role"]=="system" else 0
        user_index=count+2*(revision-1)
        if (user_index+1>=len(messages) or messages[user_index]["role"]!="user"
                or messages[user_index+1]["role"]!="assistant"):
            raise MemoryRejected("durable turn shape mismatch")
        question,raw=messages[user_index]["content"],messages[user_index+1]["content"]
        row=self.store._db.execute(
            "SELECT request_id,text FROM offline_turns WHERE session_id=? AND revision=?",
            (sid,revision),
        ).fetchone()
        if row is None or row[1]!=raw:
            raise MemoryRejected("review target does not match committed answer")
        rid=row[0]
        evidence=self.store.turn_evidence(sid,*self.scope)[revision-1]
        visible=raw
        if evidence is not None:
            result=audit_answer_faithfulness(raw,evidence)
            visible=result["published_text"]
            if type(visible) is not str:
                raise MemoryRejected("grounded publication shape mismatch")
        receipt=self.store.local_execution_receipt(sid,rid,*self.scope)
        target={"turn_revision":revision,"question_sha256":_digest(question),
                "raw_answer_sha256":_digest(raw),"visible_answer_sha256":_digest(visible)}
        return target,question,visible,stored.revision,rid,(
            receipt["execution_receipt_digest"] if receipt is not None else None)

    def _read(self,sid: str,rid: str,target: dict) -> dict|None:
        row=self.store._db.execute(
            "SELECT model_digest,tokenizer_digest,turn_revision,version,target_json,"
            "rating,flags_json,note,updated_at,content_sha256 FROM jeeves_turn_feedback "
            "WHERE session_id=? AND request_id=?",
            (sid,rid),
        ).fetchone()
        if row is None:
            return None
        model,tokenizer,revision,version,encoded,rating,flags_json,note,updated,digest=row
        try:
            pinned=_target_shape(json.loads(encoded))
            flags=_flags(json.loads(flags_json))
            if ((model,tokenizer)!=self.scope or revision!=target["turn_revision"]
                    or pinned!=target or type(rating) is not str or rating not in _RATINGS
                    or encoded!=_stable(pinned) or flags_json!=_stable(flags)):
                raise MemoryConflict("rendered answer changed; historic rating requires review")
            payload={"schema":SCHEMA,"session_id":sid,"model_digest":model,
                "tokenizer_digest":tokenizer,"target":pinned,"version":_positive(version),
                "rating":rating,"flags":flags,"note":_note(note),"updated_at":_positive(updated)}
            if _digest(_stable(payload))!=_sha(digest):
                raise MemoryRejected("feedback content digest mismatch")
            return payload|{"sha256":digest}
        except MemoryConflict:
            raise
        except (TypeError,ValueError,UnicodeError,RecursionError):
            raise MemoryRejected("stored feedback failed source validation") from None

    def inspect(self,sid: str,pin: dict) -> dict:
        pin=_target_shape(pin)
        with self.store.read_snapshot():
            target,question,visible,revision,rid,receipt=self._resolve(sid,pin["turn_revision"])
            if target!=pin:
                raise MemoryConflict("reviewed answer changed")
            feedback=self._read(sid,rid,target)
            return {"schema":REVIEW_SCHEMA,"session_id":sid,"session_revision":revision,
                    "model_digest":self.scope[0],"tokenizer_digest":self.scope[1],
                    "target":target,"feedback":feedback,"shape_diagnostics":inspect_shape(question,visible),
                    "can_prepare_followup":revision==target["turn_revision"],
                    "local_execution_receipt_digest":receipt,
                    "read_only":True,"generation_performed":False,"semantic_quality_certified":False}

    def save(self,sid: str,pin: dict,*,rating: str,flags: list[str],note: str,
             expected_feedback_sha256: str|None,approved: bool) -> dict:
        pin=_target_shape(pin)
        if approved is not True or type(rating) is not str or rating not in _RATINGS:
            raise MemoryRejected("explicit valid rating required")
        flags=_flags(flags);note=_note(note)
        if expected_feedback_sha256 is not None:
            _sha(expected_feedback_sha256)
        with self.store._transaction():
            target,_,_,_,rid,_=self._resolve(sid,pin["turn_revision"])
            if target!=pin:
                raise MemoryConflict("reviewed answer changed")
            prior=self._read(sid,rid,target)
            if (prior["sha256"] if prior else None)!=expected_feedback_sha256:
                raise MemoryConflict("feedback changed; inspect latest rating")
            payload={"schema":SCHEMA,"session_id":sid,"model_digest":self.scope[0],
                "tokenizer_digest":self.scope[1],"target":target,
                "version":prior["version"]+1 if prior else 1,"rating":rating,
                "flags":flags,"note":note,"updated_at":max(int(time.time()),prior["updated_at"] if prior else 1)}
            digest=_digest(_stable(payload))
            # The same write transaction holds the exact prior record pin.
            # Do not rewrite the committed answer or inference receipt.
            self.store._db.execute(
                "INSERT INTO jeeves_turn_feedback VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(session_id,request_id) DO UPDATE SET "
                "version=excluded.version,target_json=excluded.target_json,rating=excluded.rating,"
                "flags_json=excluded.flags_json,note=excluded.note,updated_at=excluded.updated_at,"
                "content_sha256=excluded.content_sha256",
                (sid,rid,*self.scope,target["turn_revision"],payload["version"],_stable(target),
                 rating,_stable(flags),note,payload["updated_at"],digest),
            )
            return payload|{"sha256":digest}

    def delete(self,sid: str,pin: dict,*,expected_feedback_sha256: str,approved: bool) -> dict:
        pin=_target_shape(pin);_sha(expected_feedback_sha256)
        if approved is not True:
            raise MemoryRejected("explicit rating removal required")
        with self.store._transaction():
            target,_,_,_,rid,_=self._resolve(sid,pin["turn_revision"])
            if target!=pin:
                raise MemoryConflict("review target changed")
            deleted=self.store._db.execute(
                "DELETE FROM jeeves_turn_feedback WHERE session_id=? AND request_id=? "
                "AND model_digest=? AND tokenizer_digest=? AND content_sha256=?",
                (sid,rid,*self.scope,expected_feedback_sha256),
            )
            if deleted.rowcount!=1:
                raise MemoryConflict("feedback revision conflict")
        return {"deleted":True,"previous_answer_unchanged":True,"target":pin}

    def prepare_followup(self,sid: str,pin: dict,*,mode: str,flags: list[str],note: str) -> dict:
        pin=_target_shape(pin)
        if type(mode) is not str or mode not in {"critique","refine","verify"}:
            raise MemoryRejected("unknown review mode")
        flags=_flags(flags);note=_note(note)
        with self.store.read_snapshot():
            target,_,_,revision,_,_=self._resolve(sid,pin["turn_revision"])
            if target!=pin or revision!=target["turn_revision"]:
                raise MemoryConflict("follow-up requires the latest exact reviewed turn")
            instruction={
                "critique":"Critically review your immediately preceding answer against the original user request. Identify concrete errors, unresolved requirements, assumptions and what needs verification. Do not claim that unperformed work was performed.",
                "refine":"Provide a complete improved answer to the original user request, correcting substantive problems in your immediately preceding answer. Preserve valid work, explicitly address the review priorities, and distinguish verified results from proposals.",
                "verify":"Audit your immediately preceding answer against the original user request. Separate independently verified facts from inference, uncertainty, and checks that still require external execution. Do not invent citations, test results or completed actions.",
            }[mode]
            priorities=[_FLAGS[x] for x in flags]
            text=instruction
            if priorities:
                text+="\nReview priorities:\n"+"\n".join("- "+v for v in priorities)
            if note:
                text+="\nUser review note: "+note
            if len(text.encode("utf-8"))>4096:
                raise MemoryRejected("follow-up exceeds normal chat budget")
            result={"schema":"skeleton.jeeves.review-followup.v1","session_id":sid,
                    "session_revision":revision,"target":target,"mode":mode,"flags":flags,
                    "draft":text,"draft_sha256":_digest(text),
                    "read_only":True,"generation_performed":False,
                    "requires_full_history":True,"automatic_send":False}
            result["preview_sha256"]=_digest(_stable(result))
            return result

    def recent_summary(self,*,limit: int=40) -> dict:
        if type(limit) is not int or not 1<=limit<=MAX_AGGREGATE:
            raise MemoryRejected("invalid recent feedback budget")
        with self.store.read_snapshot():
            rows=self.store._db.execute(
                "SELECT session_id,turn_revision,request_id FROM jeeves_turn_feedback "
                "WHERE model_digest=? AND tokenizer_digest=? "
                "ORDER BY updated_at DESC,session_id,request_id LIMIT ?",
                (*self.scope,limit+1),
            ).fetchall()
            ratings=Counter();flags=Counter();historical=0;unavailable=0
            for sid,revision,rid in rows[:limit]:
                try:
                    target,_,_,_,actual,receipt=self._resolve(sid,revision)
                    if actual!=rid:
                        raise MemoryRejected("feedback turn identity changed")
                    record=self._read(sid,rid,target)
                    if record is None:
                        raise MemoryRejected("feedback disappeared")
                except (MemoryRejected,MemoryConflict):
                    unavailable+=1
                    continue
                ratings[record["rating"]]+=1
                flags.update(record["flags"])
                historical+=receipt is None
        return {"model_digest":self.scope[0],"tokenizer_digest":self.scope[1],
                "reviewed_records":sum(ratings.values()),"ratings":dict(sorted(ratings.items())),
                "flag_counts":dict(sorted(flags.items())),"without_execution_receipt":historical,
                "unavailable_records":unavailable,"truncated":len(rows)>limit,
                "human_feedback_only":True,"model_training_performed":False,
                "semantic_quality_certified":False}
