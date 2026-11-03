"""Measure real native token IDs on training targets before first SGD."""
from __future__ import annotations
from dataclasses import dataclass
from .frames import paired_train
from .source import SourceScope
from .policy import SupervisedPolicy
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class Coverage:
    known:int
    unknown:int
    total:int
    fraction_ppm:int
    source_sha256:str

    def report(self)->dict:
        return {
            "known":self.known,"unknown":self.unknown,
            "total":self.total,"fraction_ppm":self.fraction_ppm,
            "source_sha256":self.source_sha256,
            "actual_native_token_ids_measured":True,
            "eval_vocabulary_fitted":False,
        }


def inspect(model,source:SourceScope)->Coverage:
    if type(source) is not SourceScope:
        reject("coverage-source")
    if not hasattr(model,"_ids") or not hasattr(model,"unk"):
        reject("coverage-native-tokenizer")
    known=unknown=0
    for pair in paired_train(source.groups):
        ids=model._ids(pair.prompt+"\n"+pair.completion)
        if not ids:
            reject("coverage-empty")
        for t in ids:
            if type(t) is not int or not 0<=t<len(model.itos):
                reject("coverage-invalid-id")
            if t==model.unk:
                unknown+=1
            else:
                known+=1
    total=known+unknown
    if total==0:
        reject("coverage-zero")
    return Coverage(known,unknown,total,known*1000000//total,
                    digest({"source":source.corpus_sha256,
                            "tokenizer_terms":list(model.itos)}))


def require_admitted(coverage:Coverage,policy:SupervisedPolicy)->None:
    if type(coverage) is not Coverage or type(policy) is not SupervisedPolicy:
        reject("coverage-policy")
    if coverage.fraction_ppm<policy.min_train_known_ppm:
        reject("coverage-training-incompatible")
