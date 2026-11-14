# Native candidate training — operator runbook (2026-11-03)

## Dependency order

1. Install a genuine, rights-reviewed local native model checkpoint.
2. Independently compute checkpoint SHA-256 and confirm its native model and
   tokenizer identities. No unapproved download or hosted provider is allowed.
3. Provide an owner-private source, output and state directory. Model roots,
   shard reads and training locks reject unsafe symlinked directories.
4. Inventory all 576 original source examples from the exact Git commit.
5. Verify original rights, normalized uniqueness and correct authored answers.
6. Partition 432 training, 72 validation and 72 holdout records with group
   isolation; no validation or holdout text is included in model.fit.
7. Compare exact source prompts with the separate 480-case real model benchmark.
   This is an exact overlap gate, not proof that all near-duplicates are absent.
8. Enforce model/tokenizer SHA identities, token recognition and memory budgets.
9. Clone the native checkpoint, acquire the model-specific POSIX process fence
   and run actual TinyTransformer SGD on admitted training examples only.
10. Verify optimizer batch source hashes, monotonic steps, runtime deadline,
    unchanged champion weights and restored candidate model identity.
11. Publish the resulting native checkpoint with no-clobber private file
    descriptors, exact size and SHA-256 identity.
12. Independently run the held-out native inference checks, benchmark corpus,
    rights review, rollback drills, consumer installation and full exact-head CI.

## Read-only inspection

    python -m skeleton.ai.runtime.operational_ai.native_candidate.cli --inventory

## Genuine candidate-only run

    python -m skeleton.ai.runtime.operational_ai.native_candidate.cli --train-native --approve-candidate-only \
      --checkpoint /trusted/models/native.json \
      --sha256 VERIFIED_CHECKPOINT_SHA256 \
      --model-sha256 VERIFIED_NATIVE_MODEL_DIGEST \
      --tokenizer-sha256 VERIFIED_TOKENIZER_DIGEST \
      --license operator_reviewed --run-id original_20261103 \
      --trainer-code-sha256 VERIFIED_GIT_SOURCE_DIGEST \
      --state-directory /private/ai/state \
      --output-directory /private/ai/candidate_weights

Never substitute example hashes for model digest or training output. Training
will fail closed if the model vocabulary, memory capacity or source rights
cannot support the requested operation.

## Release holds

This build supplies no approved weight bytes and no actual trained model.
All draft PRs remain unqualified. Do not merge or promote until final-head
Merge Readiness, Backend Quality, App E2E, Workflow Input Security, Sealed
Context Guard, Artifact Policy, Malware Gate, Repository Hygiene, Secret
Scanning and Dependency Review plus independent model rights, device, quality,
installation and recovery gates have succeeded.
