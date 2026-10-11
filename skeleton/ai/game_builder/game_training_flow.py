"""Fault-tolerant game-AI experiment training and high-information dissemination.

The training flow:
 - validates evidence/project identities and quarantined approval state;
 - groups all examples by project before splitting (no project leakage);
 - prioritizes rare/severe/uncertain families without overwriting provenance;
 - writes immutable content-addressed shards under a journaled staging tree;
 - resumes a partial run after interruption and rejects tampered shards;
 - trains a small, isolated linear review classifier with validation-only
   model selection and a fully held-out project test;
 - NEVER modifies Dragon/Jeeves/HOAG parameters or deploys its fitted weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import json
import math
import os
import re
import shutil
import tempfile

from .contracts import canonical_digest, canonical_json
from .competitive_mirror_training import TrainingCandidate, split_project
from .game_project_workspace import GameWorkspace, WorkspaceError

class TrainingFlowError(ValueError):
    """Untrusted, leaking, oversized or conflicting training experiment."""


@dataclass(frozen=True, slots=True)
class CandidateBatch:
    source_project: str
    original_almanac: str
    examples: tuple[TrainingCandidate,...]

    def __post_init__(self):
        if not isinstance(self.source_project,str) or len(self.source_project)!=64:
            raise TrainingFlowError("content-addressed original game source required")
        if not isinstance(self.original_almanac,str) or len(self.original_almanac)!=64:
            raise TrainingFlowError("independent tester/mirror almanac hash required")
        if not 2<=len(self.examples)<=512:
            raise TrainingFlowError("bounded independent project dataset required")
        for case in self.examples:
            if (not isinstance(case,TrainingCandidate)
                    or case.project_digest!=self.source_project
                    or case.split!=split_project(self.source_project)
                    or case.approval!="quarantined"):
                raise TrainingFlowError("foreign or self-approved training candidate")
        if len({x.example_id for x in self.examples})!=len(self.examples):
            raise TrainingFlowError("repeated evidence artificially inflates this project")

    def payload(self):
        return dict(source_project=self.source_project,
                    almanac=self.original_almanac,
                    split=split_project(self.source_project),
                    examples=[c.payload() for c in self.examples])


@dataclass(frozen=True,slots=True)
class FlowPlan:
    run_id: str
    source_projects: tuple[str,...]
    split_projects: tuple[tuple[str,tuple[str,...]],...]
    selected: tuple[TrainingCandidate,...]
    priority: tuple[tuple[str,int],...]
    rejected_duplicates: int
    almanac_sources: tuple[str,...]

    def payload(self):
        return dict(schema="skeleton.game_builder.training_flow_plan.v1",
                    run_id=self.run_id,projects=list(self.source_projects),
                    split_projects={s:list(projects) for s,projects in self.split_projects},
                    examples=[x.payload() for x in self.selected],
                    priority={k:n for k,n in self.priority},
                    rejected_duplicates=self.rejected_duplicates,
                    original_almanacs=list(self.almanac_sources),
                    project_split_leakage_allowed=False,
                    positive_and_negative_cases=True,
                    weights_automatically_deployed=False)


def _label(example: TrainingCandidate) -> int:
    if not isinstance(example,TrainingCandidate) or example.approval!="quarantined":
        raise TrainingFlowError("experiment requires typed quarantined evidence")
    decision=example.expected.get("decision")
    if decision=="reject":
        return 1
    if decision=="accept_witnessed_incident_only":
        return 0
    raise TrainingFlowError("unknown or unreviewed experiment target")


def _priority(case: TrainingCandidate,frequency: dict[str,int],family_count: int):
    source=case.input.get("attack_family","verified_control")
    severity=case.evidence.get("severity",2)
    if type(severity) is not int or not 0<=severity<=10:
        raise TrainingFlowError("source severity cannot be invented or outside budget")
    rarity=200//(1+frequency.get(source,0))
    diversity=80 if family_count>1 else 0
    novelty=30 if case.evidence.get("verified_control") else 0
    return min(1000,severity*50+rarity+diversity+novelty)


def plan_training_flow(batches: tuple[CandidateBatch,...],*,
                       authorized: bool,per_project_cap: int=256,
                       max_examples: int=8192) -> FlowPlan:
    if not authorized:
        raise PermissionError("game training scheduling requires source owner authority")
    if (not isinstance(batches,tuple) or not 1<=len(batches)<=256
        or any(not isinstance(b,CandidateBatch) for b in batches)
        or type(per_project_cap) is not int or not 2<=per_project_cap<=512
        or type(max_examples) is not int or not 32<=max_examples<=8192):
        raise TrainingFlowError("bounded typed game knowledge cohorts required")
    projects=[b.source_project for b in batches]
    if len(projects)!=len(set(projects)):
        raise TrainingFlowError("do not multiply weight of one game by replaying its curriculum")
    candidates=[e for b in batches for e in b.examples]
    frequency=Counter(x.input.get("attack_family","verified_control")
                      for x in candidates)
    per_group=defaultdict(list)
    dropped=0
    for batch in sorted(batches,key=lambda b:b.source_project):
        seen=set()
        selected=[]
        for example in batch.examples:
            if example.example_id in seen:
                dropped+=1
                continue
            seen.add(example.example_id)
            selected.append(example)
        selected.sort(key=lambda e:(
            -_priority(e,frequency,len(frequency)),e.example_id))
        per_group[batch.source_project]=selected[:per_project_cap]
    # Round-robin projects guarantees no single large game displaces the
    # others; rarity and severity rank *within* each original project.
    chosen=[]
    active=sorted(per_group)
    while active and len(chosen)<max_examples:
        again=[]
        for p in active:
            if len(chosen)>=max_examples:break
            if per_group[p]:
                chosen.append(per_group[p].pop(0))
            if per_group[p]:
                again.append(p)
        active=again
    split_index={s:tuple(sorted(b.source_project for b in batches
                                  if split_project(b.source_project)==s))
                 for s in ("train","validation","test")}
    if sum(len(x) for x in split_index.values())!=len(batches):
        raise TrainingFlowError("unaccounted original project split")
    source_hashes=tuple(sorted(b.original_almanac for b in batches))
    payload=dict(projects=sorted(projects),
                 selection=[x.payload() for x in chosen],
                 almanacs=source_hashes,
                 per_project_cap=per_project_cap,max_examples=max_examples)
    run=canonical_digest(payload)
    return FlowPlan(
        run,tuple(sorted(projects)),tuple(split_index.items()),
        tuple(chosen),tuple((x.example_id,_priority(x,frequency,len(frequency)))
                             for x in chosen),dropped,source_hashes,
    )


def load_quarantined_batches(workspace_root: str|Path,*,authorized: bool)->tuple[CandidateBatch,...]:
    """Verify the original quarantine receipt and SHA of every prior project.

    Files lacking an exact receipt are quarantined errors, not implicitly
    trusted. Multiple separate curricula for a project are disallowed until
    explicitly merged by an independent data steward.
    """
    if not authorized:
        raise PermissionError("source-custody dataset loading requires owner authority")
    work=GameWorkspace(workspace_root)
    folder=work.root/"training"/"quarantine"
    if folder.is_symlink() or not folder.is_dir():
        raise TrainingFlowError("training original quarantine folder missing")
    batches=[]
    seen_projects=set()
    files=sorted(folder.iterdir(),key=lambda p:p.name)
    if len(files)>1024:
        raise TrainingFlowError("quarantine exceeds consumer data intake budget")
    for path in files:
        if path.is_symlink():
            raise TrainingFlowError("untrusted game dataset symlink")
        if path.suffix==".json" and path.name.endswith(".receipt.json"):
            continue
        if not re.fullmatch(r"[0-9a-f]{64}\.jsonl",path.name) or not path.is_file():
            raise TrainingFlowError("unknown or unreviewed file in original-game quarantine")
        receipt_path=folder/(path.stem+".receipt.json")
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise TrainingFlowError("training evidence requires independent source receipt")
        if path.stat().st_size>2_000_000 or receipt_path.stat().st_size>12000:
            raise TrainingFlowError("training evidence exceeds bounded size")
        try:
            receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
            data=path.read_bytes()
            if (receipt.get("schema")!="skeleton.game_builder.training_quarantine_receipt.v1"
                or receipt.get("curriculum_digest")!=path.stem
                or receipt.get("source_sha256")!=sha256(data).hexdigest()
                or receipt.get("approved") is not False
                or receipt.get("neural_training_performed") is not False):
                raise TrainingFlowError("training source hash or publication status invalid")
            records=[json.loads(line) for line in data.decode("utf-8","strict").splitlines()]
            if len(records)!=receipt.get("examples") or not 2<=len(records)<=512:
                raise TrainingFlowError("training example count disagrees with source receipt")
            example_list=[]
            for rec in records:
                if rec.get("schema")!="skeleton.game_builder.adversarial_training_candidate.v1":
                    raise TrainingFlowError("untyped game data in reviewed quarantine")
                obj=TrainingCandidate(
                    project_digest=rec["project_digest"],split=rec["split"],
                    example_id=rec["example_id"],instruction=rec["instruction"],
                    input=rec["input"],expected=rec["expected"],
                    evidence=rec["evidence"],approval=rec["approval"])
                if canonical_json(rec)!=canonical_json(obj.payload()):
                    raise TrainingFlowError("unrecognized training candidate fields")
                example_list.append(obj)
        except (ValueError,UnicodeError,TypeError,KeyError) as exc:
            raise TrainingFlowError("quarantine evidence is invalid JSON/source data") from exc
        project=receipt.get("project_digest")
        if project in seen_projects:
            raise TrainingFlowError("multiple curricula from one project need explicit review merge")
        if not isinstance(project,str) or not re.fullmatch(r"[a-f0-9]{64}",project):
            raise TrainingFlowError("invalid project identity in quarantine")
        if receipt.get("split")!=split_project(project):
            raise TrainingFlowError("project-level split was rewritten")
        batch=CandidateBatch(project,path.stem,tuple(example_list))
        batches.append(batch)
        seen_projects.add(project)
    if not batches:
        raise TrainingFlowError("no independently sealed original game datasets found")
    return tuple(batches)


def _atomic_write(path: Path,payload: bytes):
    if path.is_symlink():
        raise TrainingFlowError("untrusted symlink in training journal")
    if not path.parent.is_dir():
        raise TrainingFlowError("unrecognized training shard parent")
    fd,tmp=tempfile.mkstemp(prefix=".training-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(payload);out.flush();os.fsync(out.fileno())
        if path.exists() or path.is_symlink():
            raise TrainingFlowError("immutable shard cannot overwrite another version")
        os.rename(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def _shards(plan: FlowPlan,shard_size: int):
    batches=defaultdict(list)
    for case in plan.selected:
        batches[case.split].append(case)
    for split in ("train","validation","test"):
        cases=sorted(batches[split],key=lambda e:(e.project_digest,e.example_id))
        for i in range(0,len(cases),shard_size):
            group=cases[i:i+shard_size]
            name=f"{split}_{i//shard_size:04d}.jsonl"
            payload=("\n".join(canonical_json(c.payload()) for c in group)
                     +"\n").encode("utf-8")
            yield name,payload,group


def materialize_training_flow(
    plan: FlowPlan,workspace_root: str|Path,*,
    authorized: bool,shard_size: int=32,interrupt_after: int|None=None,
)->dict:
    if not authorized:
        raise PermissionError("training shard publication needs owner approval")
    if not isinstance(plan,FlowPlan) or type(shard_size) is not int or not 4<=shard_size<=128:
        raise TrainingFlowError("typed reproducible training plan and bounded shard size")
    if interrupt_after is not None and (type(interrupt_after) is not int or
                                        not 1<=interrupt_after<=1024):
        raise TrainingFlowError("test interruption count exceeds budget")
    work=GameWorkspace(workspace_root)
    root=work.root/"training"/"runs"
    root.mkdir(exist_ok=True)
    if root.is_symlink():
        raise TrainingFlowError("source training root cannot be a symlink")
    stage=root/(plan.run_id+".staging")
    complete=root/plan.run_id
    if complete.exists() or complete.is_symlink():
        if complete.is_symlink():
            raise TrainingFlowError("training product pointer is a symlink")
        manifest=_load_manifest(complete/"manifest.json")
        if manifest["run_id"]!=plan.run_id:
            raise TrainingFlowError("another run displaced approved sources")
        current_plan=(canonical_json(plan.payload())+"\n").encode()
        if manifest["plan_sha256"]!=sha256(current_plan).hexdigest():
            raise TrainingFlowError("completed run does not match submitted source evidence")
        _verify_run(complete,manifest)
        return dict(**manifest,recovered=True)
    if not stage.exists():
        stage.mkdir()
    if stage.is_symlink() or not stage.is_dir():
        raise TrainingFlowError("staging project is not an ordinary directory")
    pieces=list(_shards(plan,shard_size))
    plan_data=(canonical_json(plan.payload())+"\n").encode()
    if (stage/"plan.json").exists():
        if (stage/"plan.json").read_bytes()!=plan_data:
            raise TrainingFlowError("resumed training stage belongs to different plan")
    else:
        _atomic_write(stage/"plan.json",plan_data)
    shards=[]
    for index,(name,payload,cases) in enumerate(pieces):
        file=stage/name
        if file.exists() or file.is_symlink():
            if file.is_symlink() or file.read_bytes()!=payload:
                raise TrainingFlowError("existing training shard tampered; fail closed")
        else:
            _atomic_write(file,payload)
        shards.append(dict(name=name,sha256=sha256(payload).hexdigest(),
                           bytes=len(payload),count=len(cases),
                           split=name.split("_")[0]))
        if interrupt_after is not None and index+1==interrupt_after:
            raise InterruptedError("simulated interrupted training shard run")
    manifest=dict(
        schema="skeleton.game_builder.immutable_training_shards.v1",
        run_id=plan.run_id,plan_sha256=sha256(plan_data).hexdigest(),
        shards=shards,total_examples=len(plan.selected),
        project_groups=len(plan.source_projects),
        project_split_isolation=True,
        training_evaluation_not_yet_run=True,
        deployment_approved=False,
    )
    manifest_data=(canonical_json(manifest)+"\n").encode()
    if (stage/"manifest.json").exists():
        if (stage/"manifest.json").read_bytes()!=manifest_data:
            raise TrainingFlowError("staged training ledger altered")
    else:
        _atomic_write(stage/"manifest.json",manifest_data)
    _verify_run(stage,manifest)
    if complete.exists():
        raise TrainingFlowError("training publication conflict")
    os.rename(stage,complete)
    return dict(**manifest,recovered=False)


def _load_manifest(path):
    if path.is_symlink() or not path.is_file():
        raise TrainingFlowError("missing immutable experiment evidence")
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
    except (ValueError,OSError) as exc:
        raise TrainingFlowError("training shard manifest unreadable") from exc
    if (type(obj) is not dict
        or obj.get("schema")!="skeleton.game_builder.immutable_training_shards.v1"):
        raise TrainingFlowError("unrecognized training plan format")
    return obj


def _verify_run(root,manifest):
    if not root.is_dir() or root.is_symlink():
        raise TrainingFlowError("inaccessible original training product")
    plan=(root/"plan.json")
    if plan.is_symlink() or sha256(plan.read_bytes()).hexdigest()!=manifest["plan_sha256"]:
        raise TrainingFlowError("source training plan digest changed")
    counts=0
    expected={"plan.json","manifest.json"}
    for item in manifest["shards"]:
        name=item["name"]
        if not re.fullmatch(r"(train|validation|test)_[0-9]{4}\.jsonl",name):
            raise TrainingFlowError("shard path is unsafe")
        file=root/name
        if file.is_symlink() or not file.is_file():
            raise TrainingFlowError("training shard disappeared")
        data=file.read_bytes()
        if sha256(data).hexdigest()!=item["sha256"] or len(data)!=item["bytes"]:
            raise TrainingFlowError("training shard integrity violation")
        if len(data.splitlines())!=item["count"]:
            raise TrainingFlowError("training shard example count changed")
        counts+=item["count"]
        expected.add(name)
    if counts!=manifest["total_examples"] or {
        x.name for x in root.iterdir()
    }!=expected:
        raise TrainingFlowError("unlisted extra shards or missing source evidence")


def _tokens(case: TrainingCandidate):
    """Input-only features; expected labels, approval and split are excluded."""
    evidence=case.input
    fields=[]
    for key in sorted(evidence):
        fields.append("key:"+key)
        value=evidence[key]
        if isinstance(value,str) and key in {"attack_family"}:
            fields.append("family:"+value)
        elif isinstance(value,dict):
            fields.extend("subkey:"+k for k in sorted(value)[:12])
    return tuple(sorted(set(fields)))


def _features(case: TrainingCandidate):
    slots=128
    out={}
    for token in _tokens(case):
        index=int.from_bytes(sha256(token.encode()).digest()[:4],"big")%slots
        out[index]=min(4,out.get(index,0)+1)
    return out


def _sigmoid(n):
    n=max(-30,min(30,n))
    return 1/(1+math.exp(-n))


def _quality(rows,weights,bias,threshold):
    tp=tn=fp=fn=0
    brier=0.0
    for c in rows:
        value=_sigmoid(bias+sum(weights[idx]*v for idx,v in _features(c).items()))
        label=_label(c)
        predicted=int(value>=threshold)
        if label and predicted:tp+=1
        elif label and not predicted:fn+=1
        elif not label and predicted:fp+=1
        else:tn+=1
        brier+=(value-label)**2
    count=max(1,len(rows))
    return dict(n=len(rows),tp=tp,tn=tn,fp=fp,fn=fn,
                balanced_accuracy=round(
                    ((tp/(tp+fn) if tp+fn else 0)+
                     (tn/(tn+fp) if tn+fp else 0))/2,4),
                brier=round(brier/count,6))


def train_isolated_review_ranker(plan: FlowPlan,*,authorized: bool,
                                 epochs: int=35,learning_rate: float=0.18)->dict:
    """A small experimental *review classifier*, never a deployed model.

    Fit on train-projects, choose checkpoint/threshold using only validation
    projects, report untouched test-project performance. No data available
    on every split => explicit fail-closed insufficient evidence.
    """
    if not authorized:
        raise PermissionError("isolated review experiment requires owner approval")
    if not isinstance(plan,FlowPlan) or type(epochs) is not int or not 3<=epochs<=120:
        raise TrainingFlowError("bounded experimental training run required")
    if (type(learning_rate) is not float or not 0.001<=learning_rate<=0.5
            or not math.isfinite(learning_rate)):
        raise TrainingFlowError("invalid finite training step size")
    grouped=defaultdict(list)
    for c in plan.selected:
        if c.project_digest not in plan.source_projects or c.split!=split_project(c.project_digest):
            raise TrainingFlowError("training example crossed project split")
        grouped[c.split].append(c)
    projects=dict(plan.split_projects)
    required={"train":2,"validation":1,"test":1}
    reasons=[]
    for split,min_count in required.items():
        if len(projects.get(split,()))<min_count:
            reasons.append("insufficient_"+split+"_projects")
        if len({_label(c) for c in grouped[split]})!=2:
            reasons.append("missing_"+split+"_class_balance")
    base=dict(schema="skeleton.game_builder.experimental_reviewer_fit.v1",
              source_plan=plan.run_id,
              project_counts={k:len(v) for k,v in sorted(projects.items())},
              example_counts={s:len(grouped[s]) for s in ("train","validation","test")},
              feature_spec="input_only_key_family_hash_128_v1",
              heldout_project_overlap=False,
              production_dragon_or_jeeves_weights_changed=False,
              training_artifact_approved_for_deployment=False)
    if reasons:
        return dict(**base,status="blocked",reasons=reasons,
                    training_performed=False)
    w=[0.0]*128
    bias=0.0
    selected=None
    # Only train split participates in parameter estimation. The validation
    # split selects checkpoint and threshold. Test is never touched until end.
    best=(-1.0,10.0)
    weights_by_project=Counter(x.project_digest for x in grouped["train"])
    for epoch in range(epochs):
        for case in sorted(grouped["train"],key=lambda e:(e.project_digest,e.example_id)):
            label=_label(case)
            feat=_features(case)
            probability=_sigmoid(bias+sum(w[i]*v for i,v in feat.items()))
            adjustment=learning_rate*(label-probability) / (
                max(1,weights_by_project[case.project_digest])**0.5)
            bias+=adjustment
            for i,value in feat.items():
                w[i]=max(-8,min(8,w[i]*(1-0.0001*learning_rate)
                                 +adjustment*value))
        for threshold in (0.35,0.45,0.5,0.55,0.65):
            quality=_quality(grouped["validation"],w,bias,threshold)
            key=(quality["balanced_accuracy"],-quality["brier"])
            if key>best:
                best=key;selected=(epoch+1,threshold,list(w),bias,quality)
    epoch,threshold,selected_w,selected_bias,validation=selected
    test=_quality(grouped["test"],selected_w,selected_bias,threshold)
    model=dict(weights=[round(v,8) for v in selected_w],
               bias=round(selected_bias,8),threshold=threshold,
               feature_spec="input_only_key_family_hash_128_v1")
    return dict(**base,status="experimental_fit_only",
                epochs_selected=epoch,
                train=_quality(grouped["train"],selected_w,selected_bias,threshold),
                validation=validation,test=test,
                fitted_policy_digest=canonical_digest(model),
                symbolic_policy=model,
                promotion_requires_independent_wiki_hoag_human_rights_review=True,
                training_performed=True)


__all__=[
    "TrainingFlowError","CandidateBatch","FlowPlan","plan_training_flow",
    "load_quarantined_batches",
    "materialize_training_flow","train_isolated_review_ranker",
]
