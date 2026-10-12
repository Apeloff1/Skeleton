"""Dragon adversarial mirror: reproducible evidence-risk holdout benchmark.

Runs the rule-based lens over an explicitly supplied, labeled challenge suite.
A favorable score is an *engineering signal*, never independent provenance,
a factual finding, an approved model weight, or a license to use sources.
"""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import canonical_digest
from .dragon_evidence_disagreement import three_way_evidence_risks

_MAX_CASES=64
_MAX_TERMS=16

@dataclass(frozen=True,slots=True)
class HoldoutCase:
    case_id:str
    article:str
    video:str
    update:str
    shared_terms:tuple[str,...]
    expected_polarity_conflict:bool
    reviewer_evidence_digest:str

    def __post_init__(self):
        if (not isinstance(self.case_id,str) or not 1<=len(self.case_id)<=64
            or not all(ch.isalnum() or ch in "-_." for ch in self.case_id)):
            raise ValueError("bounded holdout case identity required")
        if type(self.expected_polarity_conflict) is not bool:
            raise ValueError("externally labeled holdout outcome required")
        if (not isinstance(self.reviewer_evidence_digest,str)
            or len(self.reviewer_evidence_digest)!=64
            or any(ch not in "0123456789abcdef" for ch in self.reviewer_evidence_digest)):
            raise ValueError("external reviewer receipt digest required")


class DragonEvidenceMirror:
    @staticmethod
    def evaluate(cases:tuple[HoldoutCase,...], *,
                 reviewed_holdout:bool, independent_reviewer:bool,
                 min_cases:int=4)->dict:
        if reviewed_holdout is not True or independent_reviewer is not True:
            raise PermissionError("independently labeled holdout required")
        if (type(cases) is not tuple or
            not 4<=len(cases)<=_MAX_CASES or
            not all(isinstance(c,HoldoutCase) for c in cases)):
            raise ValueError("bounded typed challenge suite required")
        if (type(min_cases) is not int or not 4<=min_cases<=len(cases)
            or len({c.case_id for c in cases})!=len(cases)):
            raise ValueError("nonduplicate minimum holdout required")
        truth=[case.expected_polarity_conflict for case in cases]
        if not any(truth) or all(truth):
            raise ValueError("both disagreement and agreement controls required")
        results=[]
        for case in cases:
            lens=three_way_evidence_risks(
                case.article,case.video,case.update,case.shared_terms)
            predicted="possible_opposing_term_polarity" in lens["possible_conflicts"]
            results.append({
                "case_id":case.case_id,
                "reviewer_evidence_digest":case.reviewer_evidence_digest,
                "expected_conflict":case.expected_polarity_conflict,
                "detected_risk":predicted,
                "lens_digest":lens["lens_digest"],
                "correct":predicted==case.expected_polarity_conflict,
            })
        n=len(results)
        expected=sum(x["expected_conflict"] for x in results)
        tp=sum(x["expected_conflict"] and x["detected_risk"] for x in results)
        fp=sum(not x["expected_conflict"] and x["detected_risk"] for x in results)
        fn=expected-tp
        tn=n-expected-fp
        # Previous lexical baseline did not flag polarity conflicts at all.
        baseline_correct=tn+fp
        candidate_correct=tp+tn
        guard=(
            n>=min_cases and tp>0 and
            candidate_correct>baseline_correct and
            fp<=max(1,n//8) and
            fn<=expected//2
        )
        core={
            "schema":"skeleton.dragon.mirror_holdout_v1",
            "cases":n,"positive_cases":expected,
            "negative_cases":n-expected,
            "baseline_correct":baseline_correct,
            "candidate_correct":candidate_correct,
            "true_positive":tp,"false_positive":fp,
            "false_negative":fn,"true_negative":tn,
            "measured_accuracy_gain_pp":round(
                100*(candidate_correct-baseline_correct)/n,2),
            "challenge_passed":bool(guard),
            "evaluation_results":results,
            "independent_provenance_verified_by_runtime":False,
            "model_weights_promoted":False,
            "neural_training_authorized":False,
            "manual_wiki_hoag_review_required":True,
        }
        return {**core,"evaluation_digest":canonical_digest(core)}
