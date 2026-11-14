"""Train-only native tokenizer spanning real role envelopes and completions."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from skeleton.cortex.port import tokens
from .frames import FramedPair,paired_train
from .policy import SupervisedPolicy
from .source import SourceScope
from .canonical import digest
from .errors import reject


@dataclass(frozen=True,slots=True)
class AlignedVocabulary:
    terms:tuple[str,...]
    observed:int
    observed_documents:int
    corpus_sha256:str
    schema_sha256:str

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.vocabulary.v1",
            "term_count":len(self.terms),
            "observed":self.observed,
            "documents":self.observed_documents,
            "corpus_sha256":self.corpus_sha256,
            "schema_sha256":self.schema_sha256,
            "fit_validation":False,
            "fit_holdout":False,
            "fit_challenges":False,
        }


def build_aligned_vocabulary(source:SourceScope,policy:SupervisedPolicy)->AlignedVocabulary:
    if type(source) is not SourceScope or type(policy) is not SupervisedPolicy:
        reject("vocab-source-policy")
    pairs=paired_train(source.groups)
    counts=Counter()
    observed=0
    for pair in pairs:
        sample=pair.prompt+"\n"+pair.completion
        terms=tokens(sample)
        if not terms:
            reject("vocab-empty-frame")
        observed+=len(terms)
        counts.update(terms)
    included=tuple(sorted(counts))
    if "__unk__" in included:
        reject("reserved-native-token")
    if not 64<=len(included)<=policy.max_vocabulary:
        reject("native-vocab-ceiling")
    return AlignedVocabulary(
        included,observed,len(pairs),source.corpus_sha256,
        digest({"scope":"train-only-framed-chat","terms":included,
                "source":source.corpus_sha256,"rights":source.rights_sha256}),
    )
