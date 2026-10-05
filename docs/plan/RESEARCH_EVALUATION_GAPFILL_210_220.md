# Research and Evaluation Gap-fill — VOL-210..VOL-220

Status: **implementation candidate; no completion, scheduling, verification signature, SOTA authority, or production authority**

Machine candidate:
`machine/ai_research_evaluation_gapfill_candidate.json`

Exact-head validator:
`scripts/check_ai_research_evaluation_gapfill.py`

## Scope

This tranche implements eleven previously unverified masterplan volumes:

- VOL-210 Research Agent Team
- VOL-211 Literature Watch System
- VOL-212 Citation Graph Analytics
- VOL-213 Reproduction Packages
- VOL-214 Experiment Comparison
- VOL-215 Statistical Analysis
- VOL-216 Model Evaluation Harness
- VOL-217 Agent Evaluation Harness
- VOL-218 Long-Horizon Benchmarks
- VOL-219 Contamination Auditor
- VOL-220 Human Evaluation

All eleven remain explicitly queued in the continuation frontier.

## Research controls

Research teams require distinct agent identities and an independently declared
verifier. Literature triage binds source identity, trust tier, content digest,
topic match, and a deterministic backlog key while remaining side-effect free.

Citation graphs reject unknown endpoints, duplicate edges, and self-citations.
They retain evidence digests for every work node.

## Reproducibility and comparison

Reproduction packages bind one exact Git revision, environment digest, typed
artifacts, commands, and optional deterministic seed.

Experiment comparisons fail closed unless protocol, dataset, benchmark revision,
and metric set are identical. Statistical analysis is restricted to explicitly
approved deterministic methods and rejects incompatible paired samples.

## Evaluation harnesses

Model evaluation requires exact case coverage and binds its report to a quality
vector. Agent evaluation requires exact scenario coverage, action-budget
compliance, and performance-evidence identity.

Long-horizon episodes enforce bounded step counts, strictly increasing
checkpoints, non-regressing progress, and explicit autonomy-acceptance evidence.

## Claim integrity

The contamination auditor fingerprints normalized content and reports train ↔
evaluation overlap. It cannot authorize SOTA claims.

Human evaluation requires at least two independent reviewers per evaluated
item, declared rubric bounds, evidence-bound judgments, and quality-vector
identity. Human-eval reports cannot grant promotion authority.

## Tranche-level review

`research_evaluation_review.py` requires all eleven evidence digests on one
exact source revision and rejects producer/verifier identity reuse.

## AI-tree parity

Research contracts use three exact quarantine file mappings so they do not
claim ownership of unrelated AI-native research directories. Reproduction
packages extend `AIFT-ARTIFACTS`; evaluation contracts extend
`AIFT-EVALUATION`.

The candidate validator checks all twelve canonical ↔ governed mirrors plus
the exact Git object identities declared by the file-tree manifest.

## Promotion boundary

Every masterplan completion checkbox remains false. A green exact-head run
establishes implementation consistency only. Independent verification and
masterplan signing remain separate authority.
