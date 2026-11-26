"""Operator-reviewed learning examples tied to immutable local chat turns.

Feedback is a user preference signal, not an independent correctness label.
Export is an explicit, bounded, rights-attested dataset preparation operation.
No on-chat training, weight mutation, activation, external transmission or
automatic enrollment. Deleting a conversation cascades its feedback records.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import re
import unicodedata

from skeleton.ai.training.flgb_training_runtime import DatasetRights, DatasetRevision, digest_json

MAX_EXAMPLES = 256
MAX_ROWS = 64
MAX_TEXT_BYTES = 16384
MAX_EXPORT_BYTES = 512*1024
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_PIN = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "skeleton.jeeves.reviewed-feedback.v1"


class FeedbackRejected(ValueError):
    pass


class FeedbackConflict(FeedbackRejected):
    pass


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise FeedbackRejected("invalid feedback identifier")
    return value


def _pin(value):
    if type(value) is not str or not _PIN.fullmatch(value):
        raise FeedbackRejected("explicit content digest required")
    return value


def _sha(value):
    return sha256(value.encode("utf-8")).hexdigest()


def _stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return _sha(_stable(value))


def _text(value, *, empty=False):
    if (type(value) is not str or (not empty and not value.strip())
            or "\x00" in value or len(value.encode("utf-8")) > MAX_TEXT_BYTES):
        raise FeedbackRejected("invalid reviewed feedback text")
    return value


def _collapsed(value):
    return " ".join(unicodedata.normalize("NFKC",value).casefold().split())


def _turn(rows, turn_index):
    if type(turn_index) is not int or turn_index<0:
        raise FeedbackRejected("nonnegative committed turn index required")
    messages=[row for row in rows if row["role"]!="system"]
    if len(messages)%2 or turn_index>=len(messages)//2:
        raise FeedbackRejected("committed turn unavailable")
    user,assistant=messages[turn_index*2:turn_index*2+2]
    if user["role"]!="user" or assistant["role"]!="assistant":
        raise FeedbackConflict("committed conversation role sequence changed")
    return _text(user["content"]),_text(assistant["content"])


class ReviewedFeedbackStore:
    def __init__(self,store,model_digest,tokenizer_digest):
        self.store=store
        self.model_digest=_pin(model_digest)
        self.tokenizer_digest=_pin(tokenizer_digest)
        with store._transaction():
            store._db.execute("""CREATE TABLE IF NOT EXISTS offline_reviewed_feedback (
                session_id TEXT NOT NULL REFERENCES offline_sessions(session_id) ON DELETE CASCADE,
                feedback_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL CHECK(turn_index >= 0),
                row_json TEXT NOT NULL,
                row_sha256 TEXT NOT NULL,
                PRIMARY KEY(session_id,feedback_id),
                UNIQUE(session_id,turn_index)
            )""")

    def _session(self,sid):
        return self.store.load(sid,self.model_digest,self.tokenizer_digest)

    def _decode(self,raw,pin,sid,fid,turn_index):
        if type(raw) is not str or len(raw.encode("utf-8"))>4*MAX_TEXT_BYTES or _sha(raw)!=pin:
            raise FeedbackConflict("feedback record integrity failure")
        try:
            row=json.loads(raw)
            if (_stable(row)!=raw or row["schema"]!=SCHEMA or row["session_id"]!=sid
                    or row["feedback_id"]!=fid or row["turn_index"]!=turn_index
                    or row["model_digest"]!=self.model_digest or row["tokenizer_digest"]!=self.tokenizer_digest
                    or row["preference_only"] is not True or row["automatic_training"] is not False):
                raise FeedbackConflict("feedback identity mismatch")
        except (TypeError,KeyError,ValueError) as exc:
            raise FeedbackConflict("feedback record invalid") from exc
        return row

    def _load(self,sid,fid):
        found=self.store._db.execute(
            "SELECT turn_index,row_json,row_sha256 FROM offline_reviewed_feedback WHERE session_id=? AND feedback_id=?",
            (sid,fid)).fetchone()
        if found is None:
            raise FeedbackRejected("reviewed feedback not found")
        return self._decode(found[1],found[2],sid,fid,found[0])

    def _verified_source(self,saved,row):
        prompt,answer=_turn(saved.transcript.to_list(),row["turn_index"])
        if _sha(prompt)!=row["prompt_sha256"] or _sha(answer)!=row["answer_sha256"]:
            raise FeedbackConflict("reviewed turn source changed")
        return prompt,answer

    def save(self,sid,*,feedback_id,expected_revision,turn_index,prompt_sha256,answer_sha256,
             preference,correction="",training_allowed=False,rights_evidence_sha256=None):
        fid=_id(feedback_id)
        if (type(expected_revision) is not int or expected_revision<1 or
                type(preference) is not str or preference not in {"preferred","rejected","corrected"} or
                type(training_allowed) is not bool):
            raise FeedbackRejected("invalid explicit feedback policy")
        _pin(prompt_sha256);_pin(answer_sha256)
        correction=_text(correction,empty=True)
        if (preference=="corrected")!=bool(correction.strip()):
            raise FeedbackRejected("corrected feedback requires exact replacement text only")
        if training_allowed:
            if preference=="rejected":
                raise FeedbackRejected("rejected answer cannot become a positive training example")
            _pin(rights_evidence_sha256)
        elif rights_evidence_sha256 is not None:
            raise FeedbackRejected("no training rights evidence without explicit enrollment")
        with self.store._transaction():
            saved=self._session(sid)
            request={"feedback_id":fid,"turn_index":turn_index,"prompt_sha256":prompt_sha256,
                     "answer_sha256":answer_sha256,"preference":preference,"correction":correction,
                     "training_allowed":training_allowed,"rights_evidence_sha256":rights_evidence_sha256}
            existing=self.store._db.execute(
                "SELECT feedback_id,turn_index,row_json,row_sha256 FROM offline_reviewed_feedback "
                "WHERE session_id=? AND (feedback_id=? OR turn_index=?)",
                (sid,fid,turn_index)).fetchall()
            if existing:
                if len(existing)!=1 or existing[0][0]!=fid:
                    raise FeedbackConflict("turn already reviewed; delete feedback before replacing it")
                old=self._decode(existing[0][2],existing[0][3],sid,fid,existing[0][1])
                if any(old[key]!=value for key,value in request.items()):
                    raise FeedbackConflict("feedback identifier reused with changed content")
                self._verified_source(saved,old)
                return old,False
            if saved.revision!=expected_revision:
                raise FeedbackConflict("conversation revision changed")
            prompt,answer=_turn(saved.transcript.to_list(),turn_index)
            if _sha(prompt)!=prompt_sha256 or _sha(answer)!=answer_sha256:
                raise FeedbackConflict("reviewed turn digest mismatch")
            count=self.store._db.execute(
                "SELECT COUNT(*) FROM offline_reviewed_feedback WHERE session_id=?",(sid,)).fetchone()[0]
            if count>=MAX_EXAMPLES:
                raise FeedbackRejected("feedback capacity reached")
            row={"schema":SCHEMA,"session_id":sid,"model_digest":self.model_digest,
                 "tokenizer_digest":self.tokenizer_digest,"source_revision":saved.revision,
                 **request,"preference_only":True,"automatic_training":False}
            raw=_stable(row)
            if len(raw.encode("utf-8"))>4*MAX_TEXT_BYTES:
                raise FeedbackRejected("feedback record storage bound exceeded")
            self.store._db.execute("INSERT INTO offline_reviewed_feedback VALUES (?,?,?,?,?)",
                                   (sid,fid,turn_index,raw,_sha(raw)))
            return row,True

    def list(self,sid):
        with self.store.read_snapshot():
            saved=self._session(sid)
            rows=self.store._db.execute(
                "SELECT feedback_id,turn_index,row_json,row_sha256 FROM offline_reviewed_feedback "
                "WHERE session_id=? ORDER BY turn_index LIMIT ?",(sid,MAX_EXAMPLES+1)).fetchall()
            if len(rows)>MAX_EXAMPLES:
                raise FeedbackConflict("feedback capacity integrity failure")
            result=[]
            for fid,index,raw,pin in rows:
                row=self._decode(raw,pin,sid,fid,index)
                self._verified_source(saved,row)
                result.append(row)
            return {"schema":SCHEMA,"session_id":sid,"revision":saved.revision,
                    "examples":result,"training_performed":False}

    def delete(self,sid,fid,expected_sha256):
        fid=_id(fid);_pin(expected_sha256)
        with self.store._transaction():
            saved=self._session(sid)
            row=self._load(sid,fid)
            self._verified_source(saved,row)
            if _digest(row)!=expected_sha256:
                raise FeedbackConflict("feedback changed since inspection")
            self.store._db.execute(
                "DELETE FROM offline_reviewed_feedback WHERE session_id=? AND feedback_id=?",(sid,fid))
            return {"deleted_feedback_id":fid,"training_performed":False,
                    "previous_exports_revoked":False}

    def export(self,sid,*,expected_revision,training_ids,heldout_ids,dataset_id):
        """Prepare existing native specialization inputs without executing training.

        Explicit held-out allocation, exact and normalized prompt deduplication,
        per-example rights evidence, and source validation occur under one
        SQLite read snapshot. This is not independent legal/benchmark review.
        """
        dataset_id=_id(dataset_id)
        if type(expected_revision) is not int or expected_revision<1:
            raise FeedbackRejected("invalid export source revision")
        for ids in (training_ids,heldout_ids):
            if type(ids) is not list or not 1<=len(ids)<=MAX_ROWS:
                raise FeedbackRejected("explicit nonempty bounded dataset split required")
            for fid in ids:
                _id(fid)
            if len(set(ids))!=len(ids):
                raise FeedbackRejected("duplicate dataset example")
        if set(training_ids)&set(heldout_ids):
            raise FeedbackRejected("training and holdout overlap")
        with self.store.read_snapshot():
            saved=self._session(sid)
            if saved.revision!=expected_revision:
                raise FeedbackConflict("conversation changed since export review")
            result={"train":[],"heldout":[]}
            lineage=[]
            seen_prompts=set()
            seen_text=set()
            for split,ids in (("train",training_ids),("heldout",heldout_ids)):
                for fid in ids:
                    row=self._load(sid,fid)
                    if row["training_allowed"] is not True or row["preference"] not in {"preferred","corrected"}:
                        raise FeedbackRejected("example lacks explicit positive training permission")
                    _pin(row["rights_evidence_sha256"])
                    prompt,answer=self._verified_source(saved,row)
                    target=row["correction"] if row["preference"]=="corrected" else answer
                    text="user: "+prompt+"\nassistant: "+target
                    fingerprint=_sha(_collapsed(prompt))
                    text_fingerprint=_sha(_collapsed(text))
                    if fingerprint in seen_prompts or text_fingerprint in seen_text:
                        raise FeedbackRejected("duplicate normalized training or heldout prompt")
                    seen_prompts.add(fingerprint);seen_text.add(text_fingerprint)
                    result[split].append(text)
                    lineage.append({"feedback_id":fid,"split":split,"feedback_sha256":_digest(row),
                                    "prompt_sha256":row["prompt_sha256"],"target_sha256":_sha(target),
                                    "rights_evidence_sha256":row["rights_evidence_sha256"]})
            if sum(len(x.encode("utf-8")) for group in result.values() for x in group)>MAX_EXPORT_BYTES:
                raise FeedbackRejected("feedback export byte limit exceeded")
            # Match the existing native specialization digest domain exactly.
            content_digest=digest_json(result)
            rights=DatasetRights(dataset_id,"local-reviewed-chat","allowed","operator-attested",
                                 ("specialization",),digest_json(lineage))
            revision=DatasetRevision(dataset_id,0,content_digest,rights.digest,
                                     digest_json({"schema":SCHEMA,"transform":"exact-chat-pair-v1"}))
            output={"schema":"skeleton.jeeves.specialization-input.v1","session_id":sid,
                    "source_revision":saved.revision,"model_digest":self.model_digest,
                    "tokenizer_digest":self.tokenizer_digest,**result,"lineage":lineage,
                    "dataset_rights":asdict(rights),"dataset_revision":asdict(revision),
                    "dataset_revision_digest":revision.digest,
                    "operator_rights_attested_not_independently_verified":True,
                    "token_level_contamination_verified":False,
                    "training_performed":False,"activation_authorized":False,
                    "export_revocation_automatic":False}
            output["export_sha256"]=_digest(output)
            return output
