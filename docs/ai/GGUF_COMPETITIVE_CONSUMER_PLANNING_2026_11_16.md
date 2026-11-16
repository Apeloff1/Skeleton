# GGUF competitive consumer planning — 2026-11-16

This increment extends the existing operator-only planning path. It creates no
model, provider, persistence authority, runtime root or network dependency.

`python -m scripts.plan_consumer_gguf --model /private/model.gguf --auto-geometry --context 8192 --context-ladder 1024 2048 4096 8192`

Automatic geometry is restricted to known uniform GQA architectures; missing
dimensions, hybrid/recurrent/MLA architectures and mixed manual/automatic
inputs fail closed. The native context ceiling caps each estimated target.
Manual geometry remains available for separately reviewed model architectures.
The ladder is deterministic, bounded and includes remaining RAM. CPU and RAM
are supplied by the existing probe; these are not device qualification figures.
The estimator does not authenticate weights, account for all allocator overhead,
validate actual KV cache modes, load native code or prove model quality.

Competitive context: compare the same exact artifact, prompt corpus, scoring
version and hardware against Qwen, Gemma, Llama and gpt-oss candidate builds.
Record successful quality, failures, latency, peak host/device memory and
context precision separately. Large DeepSeek, Kimi and GLM systems are remote
quality reference points, not equivalent consumer hardware comparators.
No hosted fallback or automatic downloads are introduced.

## VOL-007 incremental evidence boundary

L00 existing inference owner; L01 typed bounded inputs; L02 local metadata;
L03 explicit operator-only planning; L04 no activation; L05 reject ambiguous
geometry; L06 reported remaining budget; L07 estimates separated from physical
measurement; L08 no network or provider credentials; L09 no persistent writes;
L10 regression tests; L11 architecture/source gate required; L12 rollback by
reverting this increment; L13 no qualification promotion without exact-head
tests and physical measurements. These are implementation notes, not sign-off.

Validate `python -m pytest -q tests/test_consumer_llama_budget.py tests/test_gguf_consumer_auto_geometry.py`.
