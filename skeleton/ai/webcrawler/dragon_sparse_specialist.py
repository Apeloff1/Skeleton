"""Quantized sparse interaction ranker; bounded local inference only.

The ten banks are independently trained on disjoint synthetic folds.
Each evaluation touches fifty continuous features and ninety-six hashed
categorical interaction tiles per bank, not every allocated coefficient.
Zero/unused coefficients are reported separately from allocated capacity.
"""
from __future__ import annotations

from array import array
import base64
from dataclasses import dataclass
import hashlib
import math
import sys

SCHEMA="skeleton.dragon.navigation-ranker.v5"
INPUTS=50
BANKS=10
SIZE=32768
TILES=96
SCALE=4096
MASK32=(1<<32)-1
ARCHITECTURE={"inputs":INPUTS,"banks":BANKS,"weights_per_bank":SIZE,
              "tiles":TILES,"encoding":"int16-le-base64","scale":SCALE}
_TILE_FEATURES=tuple(((k*17+3)%INPUTS,(k*29+11)%INPUTS,(k*37+23)%INPUTS) for k in range(TILES))


def tile_indices(features):
    """Unsigned 32-bit hash matches the dependency-free training script."""
    if len(features)!=INPUTS or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in features):
        raise ValueError("sparse ranker feature bounds")
    bins=[min(7,int(x*8)) for x in features]
    result=[]
    for k,(a,b,c) in enumerate(_TILE_FEATURES):
        h=((k+1)*0x9e3779b1 ^ (bins[a]+1)*0x85ebca6b ^
           (bins[b]+1)*0xc2b2ae35 ^ (bins[c]+1)*0x27d4eb2f)&MASK32
        h^=h>>16
        h=(h*0x7feb352d)&MASK32
        h^=h>>15
        result.append(INPUTS+h%(SIZE-INPUTS))
    return tuple(result)


def _finite(value,lower,upper):
    if type(value) not in (int,float) or not math.isfinite(value) or not lower<=value<=upper:
        raise ValueError("sparse training numeric witness")
    return float(value)


@dataclass(frozen=True)
class SparseBank:
    # Store immutable native-endian packed bytes, never a mutable tensor
    # exposed to callers. A memoryview avoids Python integer expansion.
    packed:bytes
    bias:float
    touched:int
    nonzero:int

    def logit(self,features,indices):
        values=memoryview(self.packed).cast("h")
        linear=sum(values[i]*x for i,x in enumerate(features))
        tiles=sum(values[i] for i in indices)*.25
        return self.bias+(linear+tiles)/SCALE


@dataclass(frozen=True)
class SparseSpecialist:
    banks:tuple[SparseBank,...]

    @classmethod
    def from_artifact(cls,value,feature_names):
        if (not isinstance(value,dict) or set(value)!={"schema","architecture","features","banks","training"}
                or value["schema"]!=SCHEMA or value["architecture"]!=ARCHITECTURE
                or value["features"]!=list(feature_names)):
            raise ValueError("sparse specialist architecture")
        training=value["training"]
        if (not isinstance(training,dict) or
                tuple(training.get(k) for k in ("curriculum","train_groups","train_candidates","development_groups",
                    "shifted_holdout_groups","holdout_candidates","epochs","folds"))!=
                ("original-sparse-conditional-navigation-v5",409600,2457600,1024,4096,24574,1,10)
                or training.get("source_bodies_used") is not False or training.get("production_quality_verified") is not False):
            raise ValueError("sparse specialist training manifest")
        report=training["report"]
        if not isinstance(report,dict) or set(report)!={"development","v4_development","shifted_holdout","v4_holdout","lexical_holdout"}:
            raise ValueError("sparse specialist report")
        for metrics in report.values():
            if not isinstance(metrics,dict) or set(metrics)!={"ndcg3","pair_accuracy","top_regret"}:
                raise ValueError("sparse metric shape")
            _finite(metrics["ndcg3"],0,1);_finite(metrics["pair_accuracy"],0,1)
            _finite(metrics["top_regret"],0,100)
        held=report["shifted_holdout"];prior=report["v4_holdout"]
        if (held["ndcg3"]<=max(prior["ndcg3"],report["lexical_holdout"]["ndcg3"])
                or held["pair_accuracy"]<=prior["pair_accuracy"] or held["top_regret"]>=prior["top_regret"]
                or report["development"]["ndcg3"]<=report["v4_development"]["ndcg3"]):
            raise ValueError("sparse specialist promotion held")
        records=value["banks"]
        if not isinstance(records,list) or len(records)!=BANKS:
            raise ValueError("sparse bank count")
        banks=[];identities=set()
        for record in records:
            if not isinstance(record,dict) or set(record)!={"weights","bias","touched","nonzero"}:
                raise ValueError("sparse bank shape")
            lines=record["weights"]
            if (not isinstance(lines,list) or len(lines)!=22 or any(not isinstance(x,str) or not 1<=len(x)<=4096 for x in lines)
                    or any(len(x)!=4096 for x in lines[:-1])):
                raise ValueError("sparse bank encoding bound")
            try:raw=base64.b64decode("".join(lines),validate=True)
            except (ValueError,TypeError) as exc:raise ValueError("sparse bank encoding") from exc
            if len(raw)!=SIZE*2 or base64.b64encode(raw).decode("ascii")!="".join(lines):
                raise ValueError("sparse bank byte identity")
            identity=hashlib.sha256(raw).hexdigest()
            if identity in identities:raise ValueError("sparse bank independence")
            identities.add(identity)
            values=array("h");values.frombytes(raw)
            if sys.byteorder!="little":values.byteswap()
            nonzero=sum(x!=0 for x in values);touched=record["touched"]
            if (type(touched) is not int or type(record["nonzero"]) is not int
                    or not 1<=nonzero<=touched<=SIZE or record["nonzero"]!=nonzero):
                raise ValueError("sparse bank coverage witness")
            bias=_finite(record["bias"],-8,8)
            if bias*SCALE!=round(bias*SCALE):raise ValueError("sparse bias quantization")
            banks.append(SparseBank(values.tobytes(),bias,touched,nonzero))
        return cls(tuple(banks))

    @property
    def capacity(self):
        return BANKS*(SIZE+1)

    @property
    def nonzero(self):
        return sum(b.nonzero+(b.bias!=0) for b in self.banks)

    def score_detail(self,features):
        indices=tile_indices(features)
        values=[bank.logit(features,indices) for bank in self.banks]
        mean=sum(values)/len(values)
        spread=math.sqrt(sum((x-mean)**2 for x in values)/len(values))
        # The curriculum uses continuous utility, not a binary probability.
        # A monotonic centered transform keeps the advisory beam score
        # bounded without asserting a calibrated real-world probability.
        score=1/(1+math.exp(-max(-40,min(40,mean-.15*spread-2.5))))
        return score,spread

    def receipt(self):
        return {"allocated_coefficients":self.capacity,"nonzero_coefficients":self.nonzero,
                "touched_weight_slots":sum(b.touched for b in self.banks),
                "active_feature_terms_per_bank":INPUTS+TILES,
                "maximum_coefficient_terms_per_evaluation":BANKS*(INPUTS+TILES+1),
                "encoding":"int16-le-base64","synthetic_training_only":True}
