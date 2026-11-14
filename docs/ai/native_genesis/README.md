# Native Genesis: original-data AI model bootstrap

This subsystem closes a missing prerequisite in the offline native AI
pipeline: creation of an actual transformer checkpoint **without requiring
unlicensed or externally downloaded weights**. It uses only the
`skeleton.cortex.TinyTransformer` architecture, the 576 original
rights-marked candidate-source examples, and deterministic initialization.
It does not ship static model weights, pretend a tiny model is state of the
art, or authorize serving a newly initialized checkpoint.

## Operational sequence

1. Admit the exact source inventory: 24 original domains × 24 cases.
2. Verify each source answer against the independent deterministic oracle.
3. Prove original training rights, unique prompts, benchmark separation, and
   group-disjoint 432/72/72 train, validation and holdout partitions.
4. Build the native tokenizer **exclusively from 432 training lines**.
5. Admit the vocabulary and estimate model parameter and memory ceilings.
6. Construct a real CPU `TinyTransformer` with operator-approved seed,
   architecture, tokenizer and position policy.
7. Produce a real native checkpoint, restore it independently, compare the
   actual model and tokenizer digests, and optionally run two-token native
   inference to verify the graph executes.
8. Publish the genesis checkpoint into a descriptor-anchored, owner-private
   directory with immutable content-addressed naming.
9. If explicitly requested, perform real SGD over a *cloned* model via the
   existing `native_candidate.CandidateTrainer`, then publish candidate-only
   weights to a separate private directory under a model-scoped lock.
10. Evaluate champion and candidate by actual inference on the untouched
    validation or holdout partitions, preserving separation of authority.

**This is a functional, bounded native AI bootstrap, not a frontier-quality
pretrained LLM.** Model capability must be measured rather than inferred.

## CLI

```sh
python -m skeleton.ai.runtime.operational_ai.native_genesis.cli --vectors
python -m skeleton.ai.runtime.operational_ai.native_genesis.cli --doctor --approve-candidate-only
python -m skeleton.ai.runtime.operational_ai.native_genesis.cli --smoke --approve-candidate-only
```

For immutable genesis publication, first provision a trusted owner-private
parent directory on a POSIX system. An operator must supply a protected
checkpoint directory with no symlinks or group/other-writable ancestors.

```sh
python -m skeleton.ai.runtime.operational_ai.native_genesis.cli \
  --bootstrap --approve-candidate-only --genesis-dir /home/operator/private/genesis
```

For real candidate-only SGD, provision **three separate** trusted private
directories for initial checkpoints, candidate checkpoints and lock state.
The code digest must be pinned to the exact reviewed trainer implementation.

```sh
python -m skeleton.ai.runtime.operational_ai.native_genesis.cli \
  --train --approve-candidate-only \
  --genesis-dir /home/operator/private/genesis \
  --candidate-dir /home/operator/private/candidates \
  --state-dir /home/operator/private/state \
  --trainer-code-sha256 REPLACE_WITH_EXACT_64_HEX_DIGEST
```

These are operational examples, not claims that the commands were executed
during source authoring. No source code commits a trained checkpoint.

## Definition of done

Source delivery requires a complete Git tree and reviewable PR diff.
Local focused tests, actual model execution, real training, security gates,
CI on the final commit and final hardware/install qualification are separate
evidence classes. Draft status remains until all mandatory evidence is
independently verified. Model release always requires separate authority.
