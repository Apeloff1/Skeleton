"""Source-scoped, independent learned claim review.

Every evaluated pair is bound to exact supplied evidence and original
candidate character spans. The scorer is a local, separately pinned NLI
classifier. Contradiction has precedence; missing/uncertain pairs never
become support. A model verdict remains fallible and is not fact certification.
"""
from __future__ import annotations

from hashlib import sha256
import re
import time

from skeleton.app.jeeves_nli import LocalNLIVerifier, digest, text_sha

SCHEMA = "skeleton.jeeves.learned-claim-review.v1"
MAX_CLAIMS = 8
MAX_SOURCES = 3
MAX_CLAIM_BYTES = 768
_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_CITATION = re.compile(r"local:[A-Za-z0-9_-]{1,128}:[0-9]+:[0-9a-f]{16}")
_INSTRUCTION = re.compile(r"\b(?:ignore (?:all |any )?(?:previous|prior|above) instructions|"
                          r"disregard (?:the |all )?(?:system|previous)|"
                          r"system prompt|new instructions?|you are now)\b",re.I)


def claim_spans(answer):
    if type(answer) is not str or not answer.strip() or len(answer.encode("utf-8")) > 16384:
        raise ValueError("bounded original candidate required")
    rows = []
    cursor = 0
    for match in _SPLIT.finditer(answer):
        if cursor < match.start():
            rows.append((cursor,match.start()))
        cursor=match.end()
    if cursor<len(answer):
        rows.append((cursor,len(answer)))
    result=[]
    for start,end in rows:
        while start<end and answer[start].isspace():
            start+=1
        while end>start and answer[end-1].isspace():
            end-=1
        if start==end:
            continue
        raw=answer[start:end]
        hypothesis=_CITATION.sub(" ",raw).strip()
        if not hypothesis:
            continue
        result.append({"start":start,"end":end,"text_sha256":text_sha(raw),
                       "hypothesis":hypothesis,"cited":sorted(set(_CITATION.findall(raw)))})
    return result[:MAX_CLAIMS],len(result)


def _sources(evidence):
    if type(evidence) is not dict or type(evidence.get("citations")) is not list or not 1<=len(evidence["citations"])<=MAX_SOURCES:
        raise ValueError("bounded grounding manifest required")
    result={}
    for row in evidence["citations"]:
        required={"citation","document_id","document_sha256","passage","passage_sha256","char_start","char_end"}
        if not isinstance(row,dict) or not required<=set(row):
            raise ValueError("invalid admitted evidence row")
        citation=row["citation"]
        if (type(citation) is not str or citation in result or not _CITATION.fullmatch(citation)
                or type(row["passage"]) is not str or not row["passage"].strip()
                or text_sha(row["passage"])!=row["passage_sha256"]
                or type(row["char_start"]) is not int or type(row["char_end"]) is not int
                or row["char_start"]<0 or row["char_end"]-row["char_start"]!=len(row["passage"])):
            raise ValueError("admitted evidence span identity mismatch")
        result[citation]=row
    return result


def review_claims(verifier, answer, evidence, *, scope, max_pairs=None, deadline=None):
    if not isinstance(verifier,LocalNLIVerifier):
        raise ValueError("explicit local NLI classifier required")
    rows,total=claim_spans(answer)
    sources=_sources(evidence)
    ceiling=verifier.policy.max_pairs if max_pairs is None else max_pairs
    if type(ceiling) is not int or not 1<=ceiling<=verifier.policy.max_pairs:
        raise ValueError("invalid learned review pair budget")
    claims=[]
    used=0
    runtime_evaluations=0
    for item in rows:
        hyp=item["hypothesis"]
        claim={"start":item["start"],"end":item["end"],"text_sha256":item["text_sha256"],
               "hypothesis_sha256":text_sha(hyp),"source_results":[]}
        if set(item["cited"])-set(sources):
            claim["disposition"]="unknown_citation"
        elif len(hyp.encode("utf-8"))>MAX_CLAIM_BYTES:
            claim["disposition"]="claim_too_long"
        elif _INSTRUCTION.search(hyp):
            claim["disposition"]="instruction_like_claim"
        else:
            # Inspect all supplied passages, even when the answer cites only
            # one. A cherry-picked citation may not hide another source's
            # contradictory classifier result.
            eligible=[row for row in sources.values() if not _INSTRUCTION.search(row["passage"])]
            skipped=len(eligible)!=len(sources)
            if not eligible or used+len(eligible)>ceiling:
                claim["disposition"]="pair_budget_or_no_evidence"
            else:
                if deadline is not None and time.monotonic()>=deadline:
                    raise TimeoutError("learned review deadline exceeded")
                scored=verifier.score_pairs([(row["passage"],hyp) for row in eligible],
                                            scope=scope,deadline=deadline)
                if len(scored)!=len(eligible):
                    raise ValueError("incomplete classifier results")
                used+=len(scored)
                for source,result in zip(eligible,scored):
                    if (result["premise_sha256"]!=source["passage_sha256"]
                            or result["hypothesis_sha256"]!=claim["hypothesis_sha256"]
                            or result["verifier_identity"]!=verifier.identity):
                        raise ValueError("learned review result identity mismatch")
                    runtime_evaluations+=not result["cache_hit"]
                    claim["source_results"].append({"citation":source["citation"],
                        "document_id":source["document_id"],"document_sha256":source["document_sha256"],
                        "passage_sha256":source["passage_sha256"],"decision":result["decision"],
                        "scores_ppm":result["scores_ppm"],"margin_ppm":result["margin_ppm"],
                        "cache_hit":result["cache_hit"]})
                decisions={r["decision"] for r in claim["source_results"]}
                cited=set(item["cited"])
                supporting=any(r["decision"]=="entailment" and
                               (not cited or r["citation"] in cited) for r in claim["source_results"])
                if "contradiction" in decisions:
                    claim["disposition"]="classifier_contradiction"
                elif supporting and not skipped and "uncertain" not in decisions:
                    claim["disposition"]="classifier_support"
                else:
                    claim["disposition"]="classifier_uncertain"
        claims.append(claim)
    statuses={row["disposition"] for row in claims}
    disposition=("contested" if "classifier_contradiction" in statuses else
                 "classifier_support_only" if claims and total==len(claims) and
                 statuses=={"classifier_support"} else "review_required")
    report={"schema":SCHEMA,"candidate_sha256":text_sha(answer),
            "verifier_identity":verifier.identity,"scope_sha256":scope,
            "grounding_context_sha256":evidence["context_sha256"],
            "claims":claims,"total_claims":total,"claims_examined":len(claims),
            "pair_limit":ceiling,"pairs_considered":used,
            "native_classifier_evaluations":runtime_evaluations,
            "disposition":disposition,"all_claims_examined":total==len(claims),
            "semantic_truth_verified":False,"scores_calibrated":False,
            "primary_model_changed":False,"automatic_delivery_authorized":False}
    report["receipt_sha256"]=digest(report)
    return report


def review_candidates(verifier, candidates, evidence, *, scope, deadline=None):
    if type(candidates) is not list or not 1<=len(candidates)<=4:
        raise ValueError("bounded candidate batch required")
    # One shared classifier-pair allowance, rather than an unbounded budget
    # per generated candidate. Equal partition prevents the first candidate
    # from exhausting every comparison.
    per=verifier.policy.max_pairs//len(candidates)
    if per<1:
        raise ValueError("insufficient classifier pair budget")
    reports=[]
    for row in candidates:
        if row["output_sha256"]!=text_sha(row["text"]):
            raise ValueError("candidate changed before classifier review")
        reports.append(review_claims(verifier,row["text"],evidence,scope=scope,
                                     max_pairs=per,deadline=deadline))
    result={"schema":"skeleton.jeeves.learned-candidate-comparison.v1",
            "verifier_identity":verifier.identity,"scope_sha256":scope,
            "candidate_reports":reports,"total_pairs":sum(r["pairs_considered"] for r in reports),
            "native_classifier_evaluations":sum(r["native_classifier_evaluations"] for r in reports),
            "pair_budget":verifier.policy.max_pairs,
            "winner_selected":False,"semantic_truth_verified":False}
    result["receipt_sha256"]=digest(result)
    return result
