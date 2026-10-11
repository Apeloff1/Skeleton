"""Crash-safe local review-model promotion: staged -> shadow -> active/rollback.

Runs genuine, independent game playtester replays for both fresh in-use and
idle-review cohorts before an advisory classifier becomes the active LOCAL
game-review ranker. Canonical game rules and Jeeves/Dragon weights are never
replaced. Promotion requires six distinct, explicit operator attestations.
Every transition has an immutable hash-chain receipt and optimistic revision.
Interrupted transactions halt until verified recovery rather than silently
claiming an installation succeeded.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
import json
import os
import re
import tempfile

from .contracts import canonical_digest,canonical_json
from .game_project_workspace import GameWorkspace
from .game_model_promotion import (
    PromotionError,PromotionStandard,PromotionEvaluation,
    evaluate_candidate,evaluate_fresh_cohort,validate_policy,
)
from .game_training_flow import FlowPlan
from .game_tester_almanac import test_game_personas,TEST_FAMILIES
from .game_learning_almanac import build_game_tester_curriculum
from .quest_scene_engine import DirectorWorld

ROLES=("wiki","hoag","mirror","human","rights","device")


@dataclass(frozen=True,slots=True)
class PromotionAttestation:
    role: str
    reviewer_id: str
    candidate_digest: str
    evaluation_digest: str
    note: str
    approved: bool

    def __post_init__(self):
        if self.role not in ROLES or not re.fullmatch(r"[a-z][a-z0-9_-]{3,63}",self.reviewer_id):
            raise PromotionError("named independent evaluator required")
        if (not 12<=len(self.note)<=1200 or type(self.approved) is not bool):
            raise PromotionError("specific signed-off assessment required")

    def payload(self):
        return dict(role=self.role,reviewer_id=self.reviewer_id,
                    candidate_digest=self.candidate_digest,
                    evaluation_digest=self.evaluation_digest,
                    note=self.note,approved=self.approved)


def _strict_read(file: Path,limit: int=4_000_000):
    if file.is_symlink() or not file.is_file() or file.stat().st_size>limit:
        raise PromotionError("local reviewer evidence missing or replaced with symlink")
    try:
        result=json.loads(file.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError,OSError) as exc:
        raise PromotionError("review registry JSON unreadable") from exc
    if type(result) is not dict:
        raise PromotionError("typed immutable reviewer evidence required")
    return result


def _exclusive(file: Path,payload: dict):
    if file.exists() or file.is_symlink():
        raise PromotionError("review source receipt already exists")
    encoded=(canonical_json(payload)+"\n").encode()
    with file.open("xb") as f:
        f.write(encoded);f.flush();os.fsync(f.fileno())


def _atomic(file: Path,payload: dict):
    if file.is_symlink() or not file.parent.is_dir():
        raise PromotionError("uncontrolled registry destination")
    encoded=(canonical_json(payload)+"\n").encode()
    fd,tmp=tempfile.mkstemp(prefix=".promotion-",dir=file.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(encoded);f.flush();os.fsync(f.fileno())
        os.replace(tmp,file)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


@contextmanager
def _mutex(root: Path):
    path=root/".promotion.lock"
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:
        raise PromotionError("another reviewer promotion is running or requires operator recovery") from exc
    try:
        with os.fdopen(fd,"w") as f:
            f.write("exclusive local reviewer update\n");f.flush();os.fsync(f.fileno())
        yield
    finally:
        path.unlink(missing_ok=True)


class ReviewerRegistry:
    def __init__(self,workspace_root: str|Path):
        workspace=GameWorkspace(workspace_root)
        self.root=workspace.root/"training"/"review_models"
        if self.root.is_symlink():
            raise PromotionError("model registry may not be a symlink")
        self.root.mkdir(exist_ok=True)
        for path in ("candidates","ledger"):
            dest=self.root/path
            if dest.is_symlink():
                raise PromotionError("review history cannot redirect outside workspace")
            dest.mkdir(exist_ok=True)
        state=self.root/"state.json"
        if not state.exists():
            _exclusive(state,self._empty())
        self.read_state()

    @staticmethod
    def _empty():
        return dict(schema="skeleton.game_builder.local_reviewer_registry.v1",
                    revision=0,ledger_head=None,active=None,previous=None,
                    candidate=None,phase="idle",attestations=[],
                    observations={},source_projects=[],standard=None,
                    last_incident=None,
                    core_ai_parameters_modified=False)

    def _journal(self):
        names=sorted(p.name for p in (self.root/"ledger").iterdir())
        if any(not re.fullmatch(r"[0-9]{6}\.json",name) for name in names):
            raise PromotionError("unknown source in immutable promotion journal")
        previous=None
        latest=None
        for index,name in enumerate(names,1):
            if name!=f"{index:06d}.json":
                raise PromotionError("promotion journal has missing transitions")
            entry=_strict_read(self.root/"ledger"/name)
            proof=entry.pop("digest",None)
            if (proof!=canonical_digest(entry) or entry.get("number")!=index
                    or entry.get("previous")!=previous):
                raise PromotionError("immutable promotion audit chain was altered")
            previous=proof
            latest=dict(entry["state"],ledger_head=proof,
                        _previous_ledger_head=entry["previous"])
        return len(names),previous,latest

    def read_state(self):
        state=_strict_read(self.root/"state.json")
        length,head,latest=self._journal()
        if state.get("schema")!=self._empty()["schema"]:
            raise PromotionError("unsupported local review-model registry")
        if state.get("revision")!=length or state.get("ledger_head")!=head:
            raise PromotionError("interrupted promotion transaction; invoke explicit recovery")
        if length and {k:v for k,v in latest.items()
                       if k!="_previous_ledger_head"}!=state:
            raise PromotionError("registry and latest immutable review record disagree")
        return state

    def recover_interrupted(self,*,authorized: bool):
        if not authorized:
            raise PermissionError("interrupted reviewer registry requires operator recovery")
        with _mutex(self.root):
            state=_strict_read(self.root/"state.json")
            length,head,latest=self._journal()
            if length==state.get("revision") and head==state.get("ledger_head"):
                return state
            if length!=state.get("revision",0)+1 or not isinstance(latest,dict):
                raise PromotionError("cannot automatically reconcile missing/corrupt promotion evidence")
            if state.get("ledger_head")!=latest.get("_previous_ledger_head"):
                raise PromotionError("journal transition not chained to prior acknowledged state")
            recovered={k:v for k,v in latest.items() if k!="_previous_ledger_head"}
            # Journal snapshots are already the exact next state.
            _atomic(self.root/"state.json",recovered)
            return self.read_state()

    def _transition(self,old: dict,updated: dict,event: str):
        if old.get("revision")!=self.read_state()["revision"]:
            raise PromotionError("stale concurrent reviewer promotion request")
        updated=dict(updated,revision=old["revision"]+1)
        # The immutable ledger stores the next state without the digest
        # pointer, so a circular SHA dependency cannot occur.
        entry=dict(number=updated["revision"],previous=old["ledger_head"],
                   event=event,state=dict(updated,ledger_head=None))
        digest=canonical_digest(entry)
        entry["digest"]=digest
        updated["ledger_head"]=digest
        _exclusive(self.root/"ledger"/f"{updated['revision']:06d}.json",entry)
        _atomic(self.root/"state.json",updated)
        return updated

    def _candidate(self,digest):
        if not isinstance(digest,str) or not re.fullmatch(r"[a-f0-9]{64}",digest):
            raise PromotionError("content-addressed model candidate required")
        doc=_strict_read(self.root/"candidates"/(digest+".json"))
        if canonical_digest(doc.get("policy"))!=digest:
            raise PromotionError("model weights changed after candidate registration")
        validate_policy(doc["policy"])
        return doc

    def stage(self,plan: FlowPlan,fit: dict,*,authorized: bool,
              standard: PromotionStandard=PromotionStandard(),champion: dict|None=None):
        if not authorized:
            raise PermissionError("staging a game-review model requires operator authority")
        evaluation=evaluate_candidate(plan,fit,standard=standard,
                                      champion=champion,authorized=True)
        if not evaluation.passed:
            return dict(status="blocked",evaluation=evaluation.payload())
        with _mutex(self.root):
            state=self.read_state()
            if state["phase"] not in {"idle","active","rolled_back"}:
                raise PromotionError("finish or abort prior shadow model before staging another")
            if state["active"] is not None:
                incumbent=self._candidate(state["active"])["policy"]
                if champion is None or canonical_digest(champion)!=state["active"]:
                    raise PromotionError("must compare new model against actually active champion")
                if canonical_digest(incumbent)!=canonical_digest(champion):
                    raise PromotionError("champion source changed during evaluation")
            doc=dict(schema="skeleton.game_builder.review_candidate.v1",
                     policy=fit["symbolic_policy"],
                     source_plan=plan.run_id,
                     evaluation=evaluation.payload(),
                     standard=standard.payload(),
                     projects=list(plan.source_projects),
                     advisory_only=True,
                     jeeves_dragon_core_weights_changed=False)
            loc=self.root/"candidates"/(evaluation.candidate_digest+".json")
            if loc.exists():
                if _strict_read(loc)!=doc:
                    raise PromotionError("candidate source identity was reused for different evidence")
            else:
                _exclusive(loc,doc)
            updated=dict(state,candidate=evaluation.candidate_digest,
                         phase="staged",standard=standard.payload(),
                         source_projects=list(plan.source_projects),
                         observations={},attestations=[],
                         last_incident=None)
            changed=self._transition(state,updated,"stage")
            return dict(status="staged",candidate=changed["candidate"],
                        evaluation=evaluation.payload(),revision=changed["revision"])

    def authorize_shadow(self,attestations: tuple[PromotionAttestation,...],*,
                         authorized: bool):
        if not authorized:
            raise PermissionError("candidate review signoff needs operator authority")
        with _mutex(self.root):
            state=self.read_state()
            if state["phase"]!="staged":
                raise PromotionError("only evaluated and staged models can enter shadow")
            doc=self._candidate(state["candidate"])
            if type(attestations) is not tuple or len(attestations)!=len(ROLES):
                raise PromotionError("all independent review roles are mandatory")
            roles={a.role for a in attestations}
            reviewers={a.reviewer_id for a in attestations}
            if roles!=set(ROLES) or len(reviewers)!=len(ROLES):
                raise PromotionError("six different reviewers across distinct review roles required")
            if any(not isinstance(a,PromotionAttestation) or not a.approved
                   or a.candidate_digest!=state["candidate"]
                   or a.evaluation_digest!=canonical_digest(doc["evaluation"])
                   for a in attestations):
                raise PromotionError("attestation does not sign exact candidate and evaluation")
            updated=dict(state,phase="shadow",
                         attestations=[a.payload() for a in attestations])
            new=self._transition(state,updated,"independent_review")
            return dict(status="shadow",revision=new["revision"],
                        candidate=new["candidate"],
                        advisory_only=True)

    def observe(self,worlds: tuple[DirectorWorld,...],*,mode: str,
                authorized: bool,quest_key: str="quest_00"):
        if not authorized:
            raise PermissionError("new independent game replay evidence requires operator authority")
        if mode not in {"usage","idle"} or type(worlds) is not tuple or not 2<=len(worlds)<=8:
            raise PromotionError("new usage or idle cohort of 2..8 original games required")
        ids=[w.digest for w in worlds if isinstance(w,DirectorWorld)]
        if len(ids)!=len(worlds) or len(set(ids))!=len(ids):
            raise PromotionError("real distinct authored test worlds required")
        state=self.read_state()
        if state["phase"] not in {"shadow","active"}:
            raise PromotionError("only independently approved model can receive real gameplay observations")
        if mode in state["observations"] and state["phase"]=="shadow":
            raise PromotionError("independent evidence mode already recorded for shadow promotion")
        prior=set(state["source_projects"])
        for event in state["observations"].values():
            prior.update(event["source_project_ids"])
        if any(key in prior for key in ids):
            raise PromotionError("new gameplay observation overlaps trained or previous test projects")
        candidate=self._candidate(state["candidate"] if state["phase"]=="shadow"
                                  else state["active"])
        policy=candidate["policy"]
        cases=[]
        receipts=[]
        for world in worlds:
            game=test_game_personas(world,quest_key,
                                    max_personas=5,
                                    mutation_families=TEST_FAMILIES,
                                    authorized=True)
            if not game.passed:
                raise PromotionError("playtested source is not a successful independent game replay")
            curriculum=build_game_tester_curriculum(game,authorized=True)
            cases.extend(curriculum.examples)
            receipts.append(dict(world=world.digest,
                                 actual_gameplay_almanac=game.digest,
                                 original_quest=quest_key,
                                 passes=game.passed,
                                 attack_count=len(game.probes)))
        standard=PromotionStandard(**{
            k:v for k,v in state["standard"].items() if k!="schema"
        })
        result=evaluate_fresh_cohort(
            tuple(cases),policy,standard=standard,
            source_projects=tuple(prior),authorized=True)
        result["replay_receipts"]=receipts
        with _mutex(self.root):
            current=self.read_state()
            if current["revision"]!=state["revision"]:
                raise PromotionError("cohort evaluated against stale active reviewer")
            observations=dict(current["observations"])
            observations[mode]=result
            phase=current["phase"]
            event="shadow_"+mode if phase=="shadow" else "live_"+mode
            if not result["passed"]:
                if phase=="active":
                    phase="rolled_back"
                    current=dict(current,active=current["previous"],
                                 last_incident=dict(reason="live_quality_regressed",
                                                    mode=mode,cohort=result))
                else:
                    phase="blocked"
                    current=dict(current,last_incident=dict(
                        reason="shadow_quality_failed",mode=mode,cohort=result))
            next_state=dict(current,phase=phase,observations=observations)
            new=self._transition(state,next_state,event)
        return dict(status=new["phase"],mode=mode,cohort=result,
                    revision=new["revision"],
                    actual_model_replayed=True,core_llm_weights_changed=False)

    def activate(self,*,authorized: bool):
        if not authorized:
            raise PermissionError("game reviewer activation requires explicit operator approval")
        with _mutex(self.root):
            state=self.read_state()
            if state["phase"]!="shadow" or set(state["observations"])!={"usage","idle"}:
                raise PromotionError("complete passing independent usage and idle evidence required")
            if any(not row["passed"] for row in state["observations"].values()):
                raise PromotionError("recent original-world model evaluation failed")
            usage=set(state["observations"]["usage"]["source_project_ids"])
            idle=set(state["observations"]["idle"]["source_project_ids"])
            if usage&idle:
                raise PromotionError("fresh gameplay cohorts share original source projects")
            self._candidate(state["candidate"])
            updated=dict(state,previous=state["active"],
                         active=state["candidate"],
                         candidate=None,phase="active",
                         observations=dict(state["observations"]))
            new=self._transition(state,updated,"activate_local_advisory_model")
            return dict(status="active",active=new["active"],
                        rollback_pointer=new["previous"],
                        revision=new["revision"],
                        jeeves_dragon_core_weights_changed=False,
                        gameplay_authority_transferred=False)

    def abort(self,reason: str,*,authorized: bool):
        if not authorized:
            raise PermissionError("model rollback requires operator authority")
        if not isinstance(reason,str) or not 15<=len(reason)<=300:
            raise PromotionError("auditable rollback reason required")
        with _mutex(self.root):
            state=self.read_state()
            if state["phase"] not in {"staged","shadow","active","blocked"}:
                raise PromotionError("no pending or active review model")
            was_active=state["phase"]=="active"
            next_state=dict(state,phase="rolled_back",
                            active=state["previous"] if was_active else state["active"],
                            candidate=None,last_incident=dict(reason=reason))
            new=self._transition(state,next_state,"operator_rollback")
            return dict(status="rolled_back",active=new["active"],
                        revision=new["revision"],
                        last_incident=new["last_incident"])

__all__=[
    "ROLES","PromotionAttestation","ReviewerRegistry",
]
