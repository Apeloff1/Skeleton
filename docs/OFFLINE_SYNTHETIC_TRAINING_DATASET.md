# Offline Foundations v1 — Synthetic training dataset

**Dataset:** \`skeleton-offline-foundations\` • **Version:** \`1.0.0\`  
**Scope:** Standalone Skeleton AI language/data processing, game-engine rule
reasoning, and offline-policy instruction following.  
**Acquisition:** No network or third-party corpus. All records are synthetic
examples generated from explicit deterministic rules. These are not private
user conversations, scraped tutorials, licensed game assets, or real-world
facts learned from external sources.

**Current milestone:** Dataset files and validation/training adapters are
committed. A successful training run, model improvement, human label review,
real-GGUF fine tuning, and production deployment are **not** claimed.

## Physical dataset and immutable evidence

\`skeleton/ai/training/datasets/offline_foundations_v1/\` contains:

| File | Contents | Records |
| --- | --- | ---: |
| \`train.jsonl\` | Supervised instruction/answer rows | 504 |
| \`validation.jsonl\` | Held-out model-development evaluation cases | 108 |
| \`test.jsonl\` | Held-out final evaluation cases | 108 |
| \`train_corpus.txt\` | **Train-only** text representation accepted by the current local-model builder | 504 |
| \`manifest.json\` | SHA-256 file digests, counts, scenario allocation, provenance declaration, permitted uses and limitations | All |

The JSONL schema is one object per line:

\`\`\`json
{
  "id": "ofv1-integer_arithmetic-00-0",
  "family": "integer_arithmetic",
  "group_id": "integer_arithmetic-scenario-00",
  "split": "train",
  "instruction": "Calculate 11 + 3. Output only the integer.",
  "response": "14",
  "oracle": "exact_integer"
}
\`\`\`

The \`id\` uniquely identifies a single instruction/answer variant. The
\`group_id\` identifies the *scenario*: all three variants of the same
scenario must remain on the same split. The \`oracle\` specifies a
deterministic rule-based validator, **not** a model confidence score.

## Coverage and intentionally honest limits

Each task family contains 20 scenarios with three different instruction
variants per scenario, for 60 examples per family and 720 total.

| Family | Expected capability | Deterministic answer reference |
| --- | --- | --- |
| Integer arithmetic | Scores, addition and multiplication | Integer arithmetic |
| Grid navigation | Move entities in two dimensions | Coordinate arithmetic |
| AABB collision | Distinguish overlap from edge contact | Half-open rectangle predicate |
| Discrete motion | Calculate final positions | Constant-velocity equation |
| Finite-state controller | Apply valid game event transitions | Transition table |
| Inventory management | Admit/reject add/remove requests | Bounded counter updates |
| Source grounding | Cite synthetic evidence; abstain when absent; resist source instructions | Grounded template |
| JSON extraction | Extract fields and apply a small update | Parsed object operations |
| Game mechanics | Damage, collectible points and cooldowns | Explicit numerical rules |
| Offline authority | Permit selected text reads; reject network and binaries | Explicit local security policy |
| Event chronology | Order events and compute elapsed ticks | Recorded timestamp rules |
| Text normalization | Normalize selected punctuation while preserving identifiers | Defined string transform |

This first curriculum is deliberately **narrow**. It proves deterministic
rule coverage, data wiring and pipeline invariants, not general language
competence. Training/evaluation share task templates; group-disjoint splits
reduce scenario-level leakage but **do not establish out-of-distribution
generalization**. Validation/test answers are plainly stored for local
scoring and are not a secret held-out benchmark. This is not a
copyright-clean certification or an independent legal review.

## Deterministic split and regeneration

The scenario number, not the individual paraphrase, controls the split:

- **Train:** groups \`00-13\` across each family (168 scenarios, 504 rows).
- **Validation:** groups \`14-16\` (36 scenarios, 108 rows).
- **Test:** groups \`17-19\` (36 scenarios, 108 rows).

The fixed generator version carries seed \`1729\` as a manifest identifier;
no random sampling is used. Numeric parameters and invented entity IDs are
derived deterministically from the scenario number. Validation/test use
disjoint parameter ranges to avoid sharing the exact generated scenario.

Both commands run locally from the repository root:

\`\`\`sh
PYTHONPATH=. python scripts/training/generate_offline_foundations.py
PYTHONPATH=. python scripts/training/verify_offline_foundations.py
\`\`\`

The generator independently reconstructs **all four data files byte-for-byte**
and compares them with the committed snapshots, in addition to the SHA-256
manifest and deterministic label oracles. For an explicit fresh export:

\`\`\`sh
PYTHONPATH=. python scripts/training/generate_offline_foundations.py \
  --output ./recreated-foundations-v1
\`\`\`

The output directory must not already exist. Validation enforces fixed
schemas, counts, group assignments, all record identities, independent
answer-oracle checks, exact prompt deduplication, checksums, and train-only
text export identity. Unlisted files are rejected.

## Governed training admission, without automatic promotion

The existing Skeleton \`DatasetRegistry\`, \`IngestEnvelope\`,
\`DatasetManifest\`, \`SyntheticDataReceipt\` and
\`DataQualityReport\` contracts are reused. Registration applies an
explicit synthetic-original rights declaration, classifications, permitted
uses, deterministic ingest identity, critical label/split quality gates
and a content-addressed dataset digest:

\`\`\`sh
PYTHONPATH=. python scripts/training/verify_offline_foundations.py \
  --register-db ./offline-training-registry.sqlite
\`\`\`

This registers a **training-ready dataset** under the existing governance
contract; it **does not train or promote a model**. Candidate weights still
require the separate training, verification, risk evaluation, rollback and
promotion controls enforced by Skeleton's training authority.

The current credential-free reference training entrypoint accepts
UTF-8 text, not instruction JSONL. The provided \`train_corpus.txt\`
contains only the 504 training examples as
\`<user>\`, \`<assistant>\`, \`<end>\` sequences.

\`\`\`sh
PYTHONPATH=. python scripts/training/verify_offline_foundations.py \
  --export-train ./train-only-copy.txt
# Optional experimental local model build. May be CPU-intensive.
PYTHONPATH=. python -m skeleton.ai.runtime.inference.train \
  ./train-only-copy.txt --output ./candidate-model.json \
  --model-id skeleton-offline-foundations-experimental \
  --hidden-size 32 --epochs 1 --seed 1729
\`\`\`

The recurrent baseline may not learn these tasks usefully; its purpose is to
verify local training and artifact generation, **not** to imply it can train
a contemporary large transformer or update a GGUF model's weights. Use an
appropriate separately governed transformer/fine-tuning pipeline for a
production-scale model.

## Holdout scoring

An external candidate generates an answer to every instruction in either
held-out split, saving one JSONL line per identity:

\`\`\`json
{"id":"ofv1-integer_arithmetic-14-0","prediction":"1512"}
\`\`\`

(This example answer is illustrative and not a verified score.)
Run local exact-match scoring:

\`\`\`sh
PYTHONPATH=. python scripts/training/verify_offline_foundations.py \
  --evaluate ./predictions.jsonl --split validation
\`\`\`

Use \`--split test\` only for a deliberate final evaluation. Missing,
duplicate, unknown or **training-set** prediction identities are refused.
Scores are reported per family and overall; answers and prompts are not
echoed. JSON output comparison ignores irrelevant key order but does not
grant partial credit or assert semantic equivalence. No fabricated model
scores, accuracy improvement or promoted-weights receipt is included.

## Threat model and red-team cases

The regression suite \`skeleton/testing/test_offline_foundations.py\`
includes:

1. Independent byte-for-byte dataset regeneration.
2. All 720 examples passing the deterministic answer oracles.
3. Scenario-group disjointness and exact prompt deduplication.
4. Cross-split alias attempts and held-out training contamination rejection.
5. Deliberately incorrect labels **with recomputed file and corpus SHA-256**,
   proving that hash checks alone do not validate truth.
6. Altered instruction text with recomputed hashes but the same answer,
   caught by independent generator equivalence.
7. Symlinked files, additional payloads, duplicate/unknown predictions and
   malformed example contracts.
8. Idempotent rights-governed registration and critical quality gating.
9. Full and intentionally incorrect held-out prediction scoring, without
   conflating a reference-answer scorer with a trained model evaluation.

No network access is required to regenerate, validate or score the dataset.
The source files are openly readable and **not an adversary-resistant
secret benchmark**. Human-reviewed tasks and real game-engine/AI observations
must be collected separately with explicit source rights, temporal fences,
independent oracles and held-out leakage controls before production training.

## Next training-data expansions

The v1 corpus is a **foundation**, not the whole training set. Next
high-value additions are genuinely executed game-engine traces, cross-era
console semantics, controlled tool-selection traces, human-labelled code
repair tasks, tokenizer stress cases, multi-step reasoning and genuinely
fresh held-out game projects. Every new acquisition should be versioned,
rights-admitted, independently evaluated and isolated from its test data.
Do not silently scrape proprietary console games, private files or
third-party model outputs as if training rights had been granted.
