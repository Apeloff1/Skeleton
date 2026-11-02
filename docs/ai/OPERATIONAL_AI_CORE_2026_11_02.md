# Operational AI core — offline inference integration, not game systems

This draft adds a **functional, model-bound, offline AI integration path** under
`skeleton/ai/runtime/operational_ai/`. It does not author game content, scenes,
quests, narrative, assets or simulation. Game-system changes belong to their
separate owners. It does **not** create a competing transformer/model-authority
implementation: the existing `NativeChatEngine`, `NativeLLMRuntime`,
`OfflineChatStore` remain source-of-truth.

## Dependency-safe construction order

| Wave | Implementation | Acceptance obligation |
| --- | --- | --- |
| MBW-00 | `authority/` strict JSON, identity, grants, finite budgets | duplicate keys, bounds, no-grant escalation |
| MBW-01 | `persistence/` hash-chain audit, durable intents, projection, backup | restart replay, tamper detection, idempotency |
| MBW-02 | `model/`, `context/` pinned real checkpoint, native generation, scoped memory and retrieval | no network fallback, exact model/tokenizer, evidence is data |
| MBW-03 | `tools/` schema registry and descriptor-anchored readonly handlers | no model-generated privilege, fail-closed writes |
| MBW-04 | `orchestration/` authoritative turn commit, retry replay, recovery | full history persists, no duplicate generation on retry |
| MBW-05 | `transport/` explicit local API and CLI | loopback only, bearer, bounded body, untrusted origin refused |
| MBW-06 | `evaluation/` versioned, measured real-model test | no fake pass/quality claims |
| MBW-07 | `deployment/` readiness inventory and verified local requirements | device, model, installer and signed CI qualification held |

## Direct executable first run

Provision a real compatible **Skeleton native-transformer checkpoint JSON**.
Verify its SHA256 independently; this command never downloads, selects a
hosted provider, or synthesizes weights:

```bash
python -m skeleton.ai.runtime.operational_ai.transport.cli \
  --checkpoint /trusted/models/native.json \
  --sha256 <actual-64-hex-sha256> \
  --license 'operator-reviewed-license-id' \
  --database /private/chat.sqlite3 \
  --memory-db /private/memory.sqlite3 \
  --journal-db /private/audit.sqlite3 \
  --message 'Explain your capabilities'
```

Preserve the emitted `session_id`, then pass `--session` with the same database
paths for the next turn. Supply stable `--request-id` on retry to replay the
committed receipt without regenerating. `--history` and `--status` are local
read paths. The same CLI supports `--serve --port 8765` after setting a strong
random `SKELETON_LOCAL_AI_BEARER` environment variable. Server binds only to
`127.0.0.1`, rejects supplied browser origins and only processes authenticated
`/v1/operations` requests. Do not expose through a public reverse proxy.

## Important limits

- The native model must already exist. Code compilation and fixture tests
  **do not** demonstrate quality or prove a usable real model exists.
- Chat state uses the existing `OfflineChatStore`; derived audit and memory
  are distinct scopes and **not** replacement conversation authorities.
- Source content/retrieval is explicitly untrusted evidence, not a tool grant.
- Model text cannot authorize tools. No shell/network/write-capable model tool
  is registered. Only a caller-controlled, expiring grant can invoke a tool.
- This is an additive integration plane. Existing mirrored modules remain
  unchanged until full parity and cutover evidence is independently accepted.
- No source-based inventory count substitutes for actual runtime readiness,
  controlled evaluation, exact-head security gates or device qualification.
- The 1.9 GB package still requires actual digest-verified and licensed
  payloads; no padding or fabricated weights will be introduced.

## Reliability and cross-plane hardening (second tranche)

- `orchestration/session_locks.py` serializes same-session operations inside one
  process, preventing duplicate compute on simultaneous stable request IDs.
  Cross-process correctness still comes from the authoritative SQLite
  optimistic revision check; these locks are **not** distributed leases.
- `model/circuit.py` limits repeated faulty local generation. An open circuit
  blocks requests instead of automatically routing to an unapproved provider.
- `context/chunks.py`, `context/provenance.py`, and `context/redaction.py` add
  exact source offsets, citation validation, and conservative credential
  redaction for untrusted evidence. No DLP completeness claim is made.
- `tools/risk.py` independently refuses undelegated actions and all write or
  external-effect handlers until their transaction/recovery semantics exist.
- `persistence/cursors.py` authenticates session- and model-bound replay
  cursors using a caller-held 32+ byte secret.
- `transport/client.py` is an authenticated loopback-only SDK client;
  `transport/events.py` pages committed audit events, **not** live tokens.
- `evaluation/attacks.py` and `evaluation/metrics.py` expose reproducible
  adversarial cases and numerical measurements without inferring model safety
  or release approval from a marker scan.

The default CI unit suite contains test-only generation fixtures; actual native
transformer execution is covered by `skeleton/testing/test_operational_ai_native.py`
and must be observed on the final GitHub head. As of this writing, skipped
GitHub checks are still holds, not passes.
