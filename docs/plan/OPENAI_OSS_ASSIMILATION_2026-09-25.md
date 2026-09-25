# OpenAI OSS Assimilation Lane

Date: **2026-09-25**

Status: **implementation candidate; exact-head CI and independent verification required**

This lane brings OpenAI-published open-source/open-weight material into the
canonical Skeleton AI tree while preserving the repository's deterministic
authority model.

## Two-lane import rule

1. **Exact upstream snapshots** live under
   `skeleton/ai/research/external/OpenAI/`. Source code is stored as
   non-executable `.txt` material. Every file is bound to the exact upstream
   commit and Git blob in `machine/openai_oss_assimilation.json`; each source
   retains its upstream license.
2. **Executable integration** lives under
   `skeleton/ai/integrations/openai_oss/`. These are bounded Skeleton adapters.
   They may import installed open-source packages at runtime, but they never
   import the research snapshots and never make upstream libraries the owner of
   Skeleton policy, memory, tools, or durable state.

## Pinned upstreams

- OpenAI Agents SDK — MIT — `525cd20f6da65f23a24ea1632ba620f6f3bd2f93`
- tiktoken — MIT — `4e71bbe0c078468e00fefbf94b39849389f346e5`
- Whisper — MIT — `86098128c0b4f24f0e2aa2994de830614b474227`
- Harmony — Apache-2.0 — `abd677f7ac962629c808197caa1feb9e3e95d2b0`
- gpt-oss — Apache-2.0 — `7b583341fe16729127f6d5b94a7b09ccae97e1a1`
- Codex — Apache-2.0 — `782826663df3e898d0c594a13f6f75cc2a498644`
- Evals — MIT for framework code; dataset licenses are deliberately not imported —
  `8eac7a7de5215c907fbddc30efdaf316913eccdd`
- Model Spec — CC0-1.0 — `7f1cf79fcb656c07f77c8d95b6fbc78dc7fac5b6`

## Executable capabilities

### Exact token accounting

`TiktokenTokenizer` provides model/encoding-specific token counts, fit checks
and bounded truncation. Special-token-looking text is rejected by default
instead of being silently treated as control tokens.

### gpt-oss / Harmony

`HarmonyGptOssCodec` renders canonical messages into the response format
required by gpt-oss and parses completion tokens back into normalized messages.
Analysis-channel material is suppressed from user-facing normalized output by
default.

`GptOssRuntimeConfig` exposes only the documented browser, Python and patch
tool classes, disabled by default. The current upstream `gpt-oss` package
requires Python 3.12, while Skeleton currently declares Python 3.11; the adapter
reports that boundary explicitly instead of adding a broken default dependency.

### Whisper

`WhisperAdapter` supports preloaded local Whisper models. Model weight download
is never implicit: a caller must explicitly enable it before the adapter invokes
the upstream loader.

### Agents SDK

`AgentsSdkBridge` can construct upstream Agent, handoff and guardrail objects,
but it accepts only explicitly sanitized context and does not transfer Skeleton
authority, policy or memory ownership to the external SDK.

### Codex

`CodexInteropPolicy` maps read-only/workspace-write/full-access sandboxes and
deny-all/auto-review approval modes. Skeleton is stricter than the compatibility
surface: workspace writes require workspace trust or explicit user action;
full access is disabled by default and requires explicit action plus active
review.

### Evals

`EvalCase` and `export_jsonl` provide deterministic benchmark interchange.
No Evals datasets were copied because upstream explicitly documents mixed
dataset licenses.

### Model Spec

The full CC0 Model Spec is retained as a pinned research snapshot.
`ModelSpecIndex` provides local section search but carries
`authoritative = False`; it cannot override Skeleton runtime policy.

## Weight and binary policy

No Whisper or gpt-oss weights, Python wheels, Rust binaries, model caches or
third-party datasets are committed. Installation/materialization remains an
explicit deployment concern with checksums and hardware policy still required
before production promotion.
