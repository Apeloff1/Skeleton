"""Independent, explicitly pinned Dragon neural navigation specialist.

A trained 10→16→1 MLP produces bounded candidate rankings from inert
metadata, never network authorization, tool arguments or generated URLs.
The bundled weights were trained on an original synthetic curriculum;
this is not a second generative LLM or production-quality evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .navigation_semantics import validate_packet,concepts,grams,digest,ROLE_GROUP,parse_rank

SCHEMA="skeleton.dragon.navigation-ranker.v1"
ENSEMBLE_SCHEMA="skeleton.dragon.navigation-ranker.v2"
CONTEXTUAL_SCHEMA="skeleton.dragon.navigation-ranker.v3"
FEATURES=("semantic","exact","concept","trigram","novelty","depth","retry",
          "jeeves_rank","variety","objective_gap")
CONTEXT_FEATURES=FEATURES+("relative_semantic","relative_exact","relative_gap","relative_retry",
    "semantic_percentile","gap_percentile","remaining_fraction","role_disagreement")
HEX=re.compile(r"[a-f0-9]{64}\Z")
MAX_ARTIFACT=128*1024


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>100:
        raise ValueError("ranker tensor value")
    return float(value)


def _vector(value,n):
    if not isinstance(value,list) or len(value)!=n:
        raise ValueError("ranker tensor shape")
    return tuple(_number(x) for x in value)


@dataclass(frozen=True)
class DragonSpecialist:
    model_digest:str
    input_weights:tuple
    hidden_bias:tuple
    output_weights:tuple
    output_bias:float
    ensemble:tuple=()
    architecture:str=SCHEMA
    feature_count:int=10

    @classmethod
    def from_bytes(cls,raw,expected):
        if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_ARTIFACT or not isinstance(expected,str) or not HEX.fullmatch(expected):
            raise ValueError("ranker artifact bound")
        if hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError("ranker artifact identity")
        value=json.loads(raw)
        if isinstance(value,dict) and value.get("schema") in {ENSEMBLE_SCHEMA,CONTEXTUAL_SCHEMA}:
            return cls._from_ensemble(value,expected)
        if (not isinstance(value,dict) or set(value)!={"schema","architecture","features","weights","training"}
                or value["schema"]!=SCHEMA or value["features"]!=list(FEATURES)
                or value["architecture"]!={"inputs":10,"hidden":16,"activation":"tanh","output":"sigmoid"}):
            raise ValueError("ranker architecture")
        w=value["weights"];training=value["training"]
        if set(w)!={"input","hidden_bias","output","output_bias"} or not isinstance(w["input"],list) or len(w["input"])!=16:
            raise ValueError("ranker weights")
        if (training.get("curriculum")!="original-synthetic-navigation-v1"
                or training.get("source_bodies_used") is not False or training.get("production_quality_verified") is not False
                or training.get("train_count")!=8192 or training.get("holdout_count")!=2048
                or not 0<=_number(training["holdout_log_loss"])<_number(training["baseline_log_loss"])
                or not .8<=_number(training["holdout_accuracy"])<=1):
            raise ValueError("ranker training manifest")
        return cls(expected,tuple(_vector(x,10) for x in w["input"]),_vector(w["hidden_bias"],16),
                   _vector(w["output"],16),_number(w["output_bias"]))

    @classmethod
    def _from_ensemble(cls,value,expected):
        contextual=value["schema"]==CONTEXTUAL_SCHEMA
        inputs,hidden=(18,48) if contextual else (10,32)
        names=CONTEXT_FEATURES if contextual else FEATURES
        output="contextual_pairwise_logit" if contextual else "pairwise_logit"
        if (set(value)!={"schema","architecture","features","members","training"}
                or value["features"]!=list(names)
                or value["architecture"]!={"inputs":inputs,"hidden":hidden,"members":3,
                                           "activation":"tanh","output":output}):
            raise ValueError("ranker ensemble architecture")
        training=value["training"]
        expected_training=("original-contextual-hard-negative-v3",4096,768,1536,16) if contextual else (
            "original-grouped-navigation-pairwise-v2",3072,512,1024,18)
        if (tuple(training.get(k) for k in ("curriculum","train_groups","development_groups","shifted_holdout_groups","epochs"))!=expected_training
                or training.get("source_bodies_used") is not False
                or training.get("production_quality_verified") is not False):
            raise ValueError("ensemble training manifest")
        if contextual and (training.get("train_candidates")!=24578 or training.get("holdout_candidates")!=9218):
            raise ValueError("contextual curriculum counts")
        report=training["report"]
        expected_metrics={"development","shifted_holdout","v1_holdout","lexical_holdout"} if not contextual else {
            "development","v2_development","shifted_holdout","v2_holdout","lexical_holdout"}
        if set(report)!=expected_metrics:
            raise ValueError("ensemble evaluation schema")
        for metrics in report.values():
            if set(metrics)!={"ndcg3","pair_accuracy","top_regret"} or any(
                    not 0<=_number(metrics[k])<=1 for k in ("ndcg3","pair_accuracy")) or _number(metrics["top_regret"])<0:
                raise ValueError("ensemble metric range")
        baseline="v2_holdout" if contextual else "v1_holdout"
        if report["shifted_holdout"]["ndcg3"]<=max(report[baseline]["ndcg3"],report["lexical_holdout"]["ndcg3"]):
            raise ValueError("ensemble qualification held")
        if contextual and (report["development"]["ndcg3"]<=report["v2_development"]["ndcg3"]
                or report["shifted_holdout"]["pair_accuracy"]<=report[baseline]["pair_accuracy"]
                or report["shifted_holdout"]["top_regret"]>=report[baseline]["top_regret"]):
            raise ValueError("contextual ensemble qualification held")
        members=value["members"]
        if not isinstance(members,list) or len(members)!=3:
            raise ValueError("ranker ensemble members")
        result=[]
        for member in members:
            if set(member)!={"input","hidden_bias","output"} or not isinstance(member["input"],list) or len(member["input"])!=hidden:
                raise ValueError("ensemble tensor shape")
            result.append((tuple(_vector(row,inputs) for row in member["input"]),
                           _vector(member["hidden_bias"],hidden),_vector(member["output"],hidden)))
        return cls(expected,(),(),(),0.,tuple(result),value["schema"],inputs)

    @classmethod
    def load(cls,path,expected):
        path=Path(path)
        if not path.is_absolute() or path.parent.resolve(strict=True)!=path.parent:
            raise ValueError("canonical local ranker path required")
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 1<=before.st_size<=MAX_ARTIFACT:
            raise ValueError("ranker artifact file bound")
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0))
        try:
            opened=os.fstat(fd)
            witness=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
            if witness(opened)!=witness(before):raise ValueError("ranker artifact replaced")
            with os.fdopen(fd,"rb",closefd=False) as read:
                raw=read.read(MAX_ARTIFACT+1)
            if witness(os.fstat(fd))!=witness(before) or witness(path.lstat())!=witness(before):
                raise ValueError("ranker artifact changed")
        finally:os.close(fd)
        return cls.from_bytes(raw,expected)

    def score_detail(self,features):
        if len(features)!=self.feature_count or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in features):
            raise ValueError("ranker feature bounds")
        if self.ensemble:
            logits=[]
            for weights,bias,output in self.ensemble:
                hidden=[math.tanh(b+sum(w*x for w,x in zip(row,features))) for row,b in zip(weights,bias)]
                logits.append(sum(w*x for w,x in zip(output,hidden)))
            mean=sum(logits)/len(logits)
            spread=math.sqrt(sum((x-mean)**2 for x in logits)/len(logits))
            # Ranking logit, not a calibrated probability of web success.
            return 1/(1+math.exp(-max(-40,min(40,mean-.15*spread)))),spread
        h=[math.tanh(b+sum(w*x for w,x in zip(row,features)))
           for row,b in zip(self.input_weights,self.hidden_bias)]
        z=self.output_bias+sum(w*x for w,x in zip(self.output_weights,h))
        return 1/(1+math.exp(-max(-40,min(40,z)))),0.

    def score(self,features):
        return self.score_detail(features)[0]

    def rank(self,group,first):
        ids=validate_packet(group)
        if len(ids)>ROLE_GROUP:raise ValueError("dragon specialist group bound")
        first=parse_rank(json.dumps(first),len(ids))
        if self.ensemble:
            from .dragon_specialist_search import beam_rank
            order,values,planner=beam_rank(self,group,first)
            receipt={"schema":"skeleton.dragon.specialist-execution.v1","model_digest":self.model_digest,
                "packet_digest":group["packet_digest"],"first_rank_digest":digest(first),
                "feature_digest":digest(values),"output_digest":digest(order),
                "candidate_count":len(ids),"inference_engine":"dragon_neural_ranker",
                "architecture":self.architecture,"member_count":len(self.ensemble),
                "mean_logit_spread":round(sum(x["ensemble_logit_spread"] for x in values)/len(values),10),
                "confidence_is_calibrated_probability":False,"planner":planner,
                "network_authorized":False,"production_quality_verified":False}
            return order,{**receipt,"execution_receipt_digest":digest(receipt)}
        q=set(group["objective"]);qc=concepts(q);qg=grams(q)
        selected=set();covered=set();values=[]
        ranks={n:1/(1+i) for i,n in enumerate(first)}
        anchor=set(group["candidates"][first[0]-1]["terms"])
        for _ in range(len(ids)):
            pool=[]
            for i,row in enumerate(group["candidates"],1):
                if i in selected:continue
                terms=set(row["terms"]);tags=concepts(terms);tg=grams(terms)
                exact=len(q&terms)/max(1,len(q))
                related=len(qc&tags)/max(1,len(qc))
                fuzzy=len(qg&tg)/max(1,len(qg|tg))
                novelty=len(terms-anchor)/max(1,len(terms))
                variety=len(terms-covered)/max(1,len(terms))
                gap=len((q-covered)&terms)/max(1,len(q-covered))
                features=(row["semantic"]/1000,exact,related,fuzzy,novelty,
                          row["depth"]/3,row["attempts"]/3,ranks.get(i,0),variety,gap)
                score,spread=self.score_detail(features)
                pool.append((score,i,features,spread))
            score,i,features,spread=max(pool,key=lambda item:(item[0],-item[1]))
            selected.add(i);covered.update(group["candidates"][i-1]["terms"])
            values.append({"index":i,"score":round(score,10),"features":[round(x,10) for x in features],
                           **({"ensemble_logit_spread":round(spread,10)} if self.ensemble else {})})
        order=[row["index"] for row in values]
        receipt={"schema":"skeleton.dragon.specialist-execution.v1","model_digest":self.model_digest,
            "packet_digest":group["packet_digest"],"first_rank_digest":digest(first),
            "feature_digest":digest(values),"output_digest":digest(order),
            "candidate_count":len(ids),"inference_engine":"dragon_neural_ranker",
            "network_authorized":False,"production_quality_verified":False,
            **({"architecture":self.architecture,"member_count":len(self.ensemble),
                "mean_logit_spread":round(sum(x["ensemble_logit_spread"] for x in values)/len(values),10),
                "confidence_is_calibrated_probability":False} if self.ensemble else {})}
        return order,{**receipt,"execution_receipt_digest":digest(receipt)}


def configured_specialist(expected):
    raw=os.getenv("SKL_DRAGON_SPECIALIST_JSON","")
    if not raw or len(raw)>4096:raise ValueError("independent Dragon weights not configured")
    value=json.loads(raw)
    if (not isinstance(value,dict) or set(value)!={"path","sha256"}
            or value["sha256"]!=expected):
        raise ValueError("independent Dragon weight pin differs")
    return DragonSpecialist.load(value["path"],expected)
