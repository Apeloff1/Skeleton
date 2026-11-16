# Jeeves measured local efficiency — operator integration and qualification

This increment extends the existing local inference owner (VOL-007/VOL-015, runtime inference). It is not a second provider, model, storage authority, or weight-training system. It uses local GGUF configuration planning and measured evidence rather than guesses about GPU/CPU speed.

## Improvements

- Consumer admission preserves both the configured and budgeted scratch/KV reserves, using the larger value, and honors the explicit budget context ceiling.
- A finite search space proposes up to twelve CPU thread/prefill batch combinations under the existing context, model, precision, GPU and resource ceilings.
- Model, runtime, tokenizer, host profile, corpus and benchmark protocol must be pinned independently. No raw prompt, weight, path or environment values are published in the profile ID.
- Paired repeated trials must have equal prompt and generated token counts, successful completion, acceptable absolute quality, no per-trial quality downgrade, bounded measured peak memory and no unacceptable latency regression.
- Select only when median end-to-end latency improves by at least the configured threshold (default 5%). Baseline remains the recommendation for absent/incomplete/failed evidence. An unqualified baseline is a hold, not approval to serve it.
- No automatic deployment, inference retry, remote acquisition, replacement of model bytes, or escalation of permissions.

## Operator usage (existing configuration and observed data)

```python
from skeleton.ai.runtime.inference.measured_tuning import (
    TuningScope, Sample, candidates, corpus_identity, select,
)

# config and hardware_budget are the existing typed local planner inputs.
# All six identity hashes must originate from operator-owned verified sources.
scope = TuningScope(model_sha, runtime_sha, tokenizer_sha, host_sha,
                    corpus_identity(case_shas), protocol_sha)
profiles = candidates(config, hardware_budget, model_bytes=verified_size,
                      scope=scope)
# Independently run approved local GGUF trials for every candidate, same
# fixed corpus/repeat index, controlled cache state, output budget and seed.
# Convert trustworthy observations to Sample objects, including failures.
decision = select(profiles, observations, case_ids=tuple(case_shas))
# A human reviews the evidence, not merely the digest.
# Revalidate artifact identity and current hardware before approving a change.
```

Use actual backend measurements for TTFT, full response time and process-tree
peak memory. For GPU qualification collect allocation and device metrics
separately; this initial CPU shape search does not infer a GPU allocation.
Do not substitute estimated bytes for measured peak memory, cached replay
for live tokens, or server wall time for TTFT. If a runtime exposes only
post-commit chunking, it cannot qualify true first-token latency.
Use independent task-specific quality judgment under a fixed protocol,
rather than a model's unsupported assertion that its output is correct.
The sample schema is not a signature or an independent evidence authority.

## Evaluation / security / rollback

- Compare cold and warm runs separately via different protocol identities.
- Use fixed-length deterministic completion and code tasks with independent
  checks; do not treat a faster but shorter answer as an improvement.
- Pin physical host and software/backend fingerprints. Requalify on driver,
  model, runtime, tokenizer, cache policy, OS or hardware changes.
- Explicitly capture failed trials, OOM, cancellation and throttling.
  Do not discard outliers; each matched trial must satisfy the regression gate.
- Apply only after fresh unchanged canonical admission and explicit operator
  review. Revert to original approved manifest on regression; uncertain
  native effects remain fenced by the existing execution authority.
- Keep current provider, rights, source custody, SQLite and private state
  boundaries. No persistent tuning ledger or customer prompt collection.
- Source tests:
  `python -m unittest discover -s skeleton/testing -p 'test_jeeves_measured_tuning.py' -v`
- Run existing local inference suites and canonical architecture, construction,
  interface, provider bootstrap, enterprise superiority and implementation
  notes validators, AI tree parity and exact-head security/CI.
- Independently qualify real GGUF model on representative CPU and GPU hosts,
  including Windows/WSL2, thermals, long-run pressure, and fresh admission.

References for future measured work: upstream llama.cpp speculative decoding
documentation, completion prompt-cache and batch documentation, and server
KV-cache documentation. Adaptive speculative decoding, prefix-cache custody,
quantized KV precision comparisons, retrieval reranking and true native
streaming are **not** claimed by this change. Nor does this change alter neural
weights, increase the trained context window, certify inference speed or
automatically tune the desktop native child. Those need explicit integration
and independently measured local evidence.
