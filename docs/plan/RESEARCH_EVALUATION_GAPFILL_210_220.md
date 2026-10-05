# Research & Evaluation Gap-fill — VOL-210..VOL-220

Status: **implementation candidate; no completion, signature, scheduling, promotion, or production authority**

This batch materializes the eleven deferred research/evaluation volumes whose masterplan entries still pointed to planned tests.

It composes the existing `skeleton/ai/runtime/deferred/research_evaluation.py` primitives with a new assurance layer:
`skeleton/ai/runtime/deferred/research_evaluation_assurance.py`.

The assurance layer adds role-template and VS-003 binding, literature source/license/backlog triage, citation support/contradiction analytics, revision-bound reproduction packages, experiment-comparison eligibility, approved statistical plans, model/agent evaluation acceptance evidence, bounded long-horizon acceptance, contamination fingerprint evidence, and blinded human-evaluation/quality-vector binding.

Every VOL-210..VOL-220 planned test placeholder is replaced by an executable focused regression under `skeleton/testing`.

AI-tree ownership is expanded without changing canonical source object identities:
- VOL-210..211 -> AIFT-SOCIAL
- VOL-212 -> AIFT-RESEARCH-SOURCE-LINEAGE
- VOL-213 -> AIFT-RESEARCH
- VOL-214..220 -> AIFT-EVALUATION

All eleven volumes remain explicitly queued and unscheduled. Completion checkboxes and all signing/promotion authority remain false. A green exact-head workflow is evidence for one revision only and does not independently close the volumes.
