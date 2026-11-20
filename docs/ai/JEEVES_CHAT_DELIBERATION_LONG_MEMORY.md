# Jeeves reviewed deliberation and semantic memory

## Execution contract

The ordinary chat path remains available. A reviewed deliberation request explicitly selects direct, refine, or review execution. Refine performs a draft pass and a final pass; review adds a critique pass. These are sequential calls to the selected local generation backend, not simulated role labels or independent model verification. Only the final answer enters the transcript. A sidecar receipt records the plan and committed execution identity without storing intermediate reasoning text.

The plan binds the exact conversation revision, message, policy, approved memory selection, and context. The server recreates the plan before admission. An invalid, stale, over-budget, cancelled, or failed plan must not become a successful final turn. A fork or imported conversation does not acquire the execution evidence of its source conversation.

## Context modes

Preserve retains the available history under the configured admission budget. Recall selects recent turns and bounded exact excerpts from older dialogue. The older fragments are extractive, not an abstractive or independently validated semantic summary. Approved memory can be explicitly selected separately. Review the selected sources before sending a planned turn.

## Optional sentence encoder

The transformer-memory adapter accepts explicitly configured compatible local ONNX and tokenizer JSON assets. The installer pins their SHA-256 identifiers and performs an encoder smoke operation before committing the installation. See `python -m skeleton.app.jeeves_transformer_memory_cli --help` for installation and management options. No pretrained model, dependency installation, network download, or pretrained quality claim is part of this branch. Treat model files as trusted operator-provided artifacts; this adapter is not a sandbox for hostile graphs.

The separate dense index is revision-bound. Rebuilding and refreshing it requires explicit authorization. The search path checks freshness, computes cosine similarity, and uses bounded candidate selection; approximate large-index retrieval is not an exhaustive nearest-neighbor guarantee. Model and tokenizer identities are part of the scope. Stale or corrupted artifacts are rejected instead of treated as current retrieval evidence.

## Qualification

Run the targeted contract suites after assembling the branch:

```sh
python -m unittest skeleton.testing.test_jeeves_deliberation skeleton.testing.test_jeeves_transformer_memory
```

Fixtures test contracts, not pretrained intelligence. The optional synthetic CPU ONNX graph exercises actual runtime execution when its dependencies are present. A skipped runtime case is not native or pretrained acceptance. Full qualification requires exact-head CI, real local native and GGUF executions, compatible pretrained encoder assets, and measured retrieval quality and cost. The live chat benchmark accepts explicit deliberation and retention strategies; its protocol digest distinguishes those policies, and matched comparisons must use the same protocol. No competitive score is asserted without recorded runs.

This change does not implement native multimodal understanding, independent semantic verification, or an automatic release authorization.
