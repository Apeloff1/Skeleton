# xAI / Grok OSS Assimilation Lane

Date: **2026-09-25**

Status: **implementation candidate; exact-head CI and independent verification required**

This lane imports the useful public xAI/Grok surface into the canonical
`skeleton/ai` tree without making xAI code, credentials, prompts, provider
objects, or remote tool execution authoritative for Skeleton.

## Pinned sources

The runtime-admitted sources are Apache-2.0:

- `xai-org/grok-1` at
  `7050ed204b8206bb8645c7b7bbef7252f79561b0`
- `xai-org/grok-build` at
  `f0e3be1100ef5252488e3be8bb0e91cf68d8c305`
- `xai-org/grok-build-plugin-cc` at
  `92b76a670713335229644e94add15ab40c80e547`
- `xai-org/xai-sdk-python` at
  `47125e210ed7e0c5056464b476ce6efce8e6c56d`
- `xai-org/xai-proto` at
  `c22ad8b1d87375ab8796b224aa56785ed922eb0d`

Exact snapshots live under
`skeleton/ai/research/external/xAI/` as non-executable `.txt` material.
`machine/xai_grok_oss_assimilation.json` binds every snapshot to its source
repository, commit, Git blob, license evidence, and destination.

## Explicitly excluded sources

Two public xAI repositories are inventoried but not copied:

- `xai-org/grok-prompts` is AGPL-3.0-only. It stays metadata-only until the
  repository owner deliberately accepts the copyleft implications.
- `xai-org/xai-cookbook` uses a custom Beta Testing License whose text says
  the software is intended solely for testing and evaluation. It is not
  promoted into Skeleton.

This is a license boundary, not a capability claim.

## Grok-1

The open-weight Grok-1 release contributes architecture knowledge and reference
inference code. The Skeleton descriptor records the published model shape:
314B total parameters, 8 experts with 2 active per
token, 64 layers, 48 query heads, 8 key/value heads, 6144 embedding width,
131072-token vocabulary, and an 8192-token maximum context.

Weights are not committed. `Grok1ModelMaterialization` requires either a
local artifact or explicit network authorization and source information.

## Grok Build control-plane primitives

The Grok Build source is useful primarily for deterministic runtime mechanics.
Skeleton promotes clean-room equivalents for:

- tool approval ceilings;
- read/search versus mutating-tool admission;
- first-party MCP ownership precedence;
- ambiguity rejection instead of startup-order wins;
- bounded per-session MCP tool caps;
- path-safe checkpoint namespaces;
- durable checkpoint design research;
- cross-agent delegation/session-transfer contracts.

Skeleton remains stricter where appropriate: remote MCP is never admitted from
an empty allowlist, and xAI unattended execution never overrides Skeleton's
own capability grants.

## Official xAI SDK provider edge

The pinned official Python SDK is version 1.20.0, Apache-2.0, and supports
Python >=3.10, so it is compatible with Skeleton's Python 3.11 baseline.

`XAIProviderEdge` keeps credentials ephemeral: API keys are passed directly
to client creation and are not fields in `XAIProviderConfig`.

Server-side tools are disabled by default. Enabling the provider-level switch
still does not authorize individual tools: `XAIServerToolPolicy` must
explicitly admit each tool class.

Sensitive OpenTelemetry attributes are disabled by default policy. A deployment
that opts into them must do so deliberately.

## Server-side tools

The official SDK/proto surface exposes web search, X search, code execution,
collections search, MCP, attachment search, and image generation.

The Skeleton builder adds stricter admission:

- web allow/exclude domain lists are mutually exclusive and bounded to five;
- X allow/exclude handle lists are mutually exclusive;
- collections searches require one to ten explicit collection IDs;
- remote MCP requires HTTPS and a non-empty explicit tool-name allowlist;
- code execution and image generation require explicit policy admission.

Provider credentials, MCP authorization values, and extra headers are runtime
arguments rather than durable tool specifications.

## Public protobuf contracts

Pinned xAI protobufs preserve the public Chat, Files, Image, Video, tool-call,
reasoning-effort, usage, streaming, deferred-completion, storage, compaction,
and multimodal contract surface as research material. Canonical Skeleton
contracts remain provider-neutral.

## Validation

`scripts/check_xai_grok_oss_assimilation.py` verifies:

- exact Git blob parity for copied snapshots;
- quarantine path and non-executable suffixes;
- Apache-2.0 disposition for executable sources;
- metadata-only treatment for AGPL/custom-license repositories;
- adapter syntax and research/runtime isolation;
- explicit credential and server-tool authority rules.

Focused tests cover the same boundaries plus Grok-1 materialization, MCP
collision planning, approval behavior, provider configuration, telemetry
policy, server-side tool validation, and delegation determinism.

No completion or verification signoff is implied until exact-head CI and
independent verification pass.
