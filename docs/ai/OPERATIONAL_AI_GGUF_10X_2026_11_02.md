# Skeleton AI — real offline GGUF, durable sessions and governed production (2026-11-02)

This change is **AI execution infrastructure**, deliberately separate from the game
builder. Its purpose is to make an operator-installed local language model usable
with verifiable identity, private memory, budgets, real inference, non-escalating
tool authority, durable conversation persistence, and measured quality checks.

## Build order and authority

| MBW stage | New source plane | Executable responsibility |
| --- | --- | --- |
| MBW-00 | Existing `operational_ai/authority` | Existing contract, owner, scope and resource limits remain canonical |
| MBW-01 | `persistence/durable` | Private SQLite operation records, CAS transitions, event chain, request idempotency, worker leases, transactional outbox/inbox and snapshots |
| MBW-02 | `model/gguf`, `model/distributed` | Cryptographically verified <=99 MB operator-installed GGUF shards, immutable Linux sealed memfd activation, real llama.cpp invocation, local worker admission and bounded microbatch planning |
| MBW-02 | `context/grounding`, `context/sealed_memory` | Source-bound FTS retrieval, exact offset citations, rank fusion, prompt-injection quarantine, AES-256-GCM private memory with per-scope HKDF keys |
| MBW-03 | `tools/secure` | Frozen tool schemas, HMAC caller grants, independent risk policy, bounded execution and read-only descriptor-anchored files |
| MBW-04 | `orchestration/workflows` | Validated DAG, finite workflow budgets, cancellation, fair tenant queue, checkpoint hashes and conservative retries |
| MBW-05 | `transport/gguf_chat.py`, `transport/live` | Actual GGUF output connected to `OfflineAIService`, durable conversation and authenticated journal cursor replay |
| MBW-06 | `evaluation/benchmarks`, `evaluation/learning` | Measured benchmarks, contamination, paired change, safety/quality/rights/consent gates and quarantined candidate lineages |
| MBW-07 | `deployment/operator` | Read-only doctor, capacity admission and exact-head, no-skipped-check release refusal |

The existing source mirror governance is preserved: all new modules live under
the native `skeleton/ai/runtime/operational_ai` owner, not the source-equivalence
mirrors of `skeleton.ai.runtime.inference` or `skeleton.ai.runtime.persistence`.
The already-existing `machine/ai_ecosystem_bundle_v1.json` stage prefix map
assigns the new modules automatically to the canonical MBW waves.

## Real executable path

```
operator-owned checkpoint GGUF on local disk
  -> `prepare_gguf`: split into <=95 MB shards, hash every byte
  -> `GGUFModelManifest`: source/license/rights + exact composite identity
  -> `assemble_model`: openat nofollow, digest shards, seal memfd
  -> `GGUFBackend`: real local llama-cpp-python token generation
  -> `ModelGateway`: model/tokenizer identity and token budget checks
  -> `OfflineAIService`: native engine + existing SQLite chat authority
  -> AES-GCM sealed scoped memory + hash-chained audit journal
  -> private loopback, bearer-authenticated HTTP / local CLI
```

**No model weights are included in source Git.** The local model MUST actually
exist, have approved rights and pass both SHA-256 checks. The GGUF backend does
not synthesize a response or fall back to a hosted provider when llama.cpp is
missing. It will refuse to start if the model cannot be held as an immutable
sealed image or physical memory admission fails. For CPU-only setups, choose
`--gpu-layers 0`; any GPU acceptance is observational and requires an independent
target-device test.

### Prepare your own model, offline

Linux requirements: Python >=3.11, local `llama-cpp-python` installed from a
trusted, reviewed build, local-model readable permissions, enough RAM to hold a
second copy of the model, and `/proc/self/fd` + sealed `memfd_create` support.
There is intentionally no automatic pip installation, network fetching or model
download in the deployment path.

A model of 1.8 GB typically produces around twenty 95 MB shards. The **2 GB PR
limit** is satisfied by leaving binaries outside Git; the **100 MB per file**
ceiling is satisfied by each archived operator shard. The archive itself is an
external release artifact, not a file added to Git or counted as finished until
verified in the target environment.

Create a private operator directory and a private state directory (mode 0700).
Then run (replace values with real, independently verified provenance):

```bash
python -m skeleton.ai.runtime.operational_ai.model.gguf.prepare_cli \
  --input /private/model/approved-original.gguf \
  --output-dir /private/approved-model-shards \
  --model-id local_approved \
  --license 'YOUR_VERIFIED_MODEL_LICENSE' \
  --source 'operator-owned:YOUR_CHECKPOINT_PROVENANCE' \
  --rights-approved --context 8192 --memory-bytes 4000000000
```

This creates `model.manifest.json`, `approved_artifacts.json`, and small
`weights/local_approved_part_*.ggufpart` files. All input bytes are read from
the operator's real model and checked against a SHA-256 ledger. No padding.
Source Git is not modified.

Verify a completed model without claiming real inference:

```bash
python -m skeleton.ai.runtime.operational_ai.transport.gguf_cli verify \
  --root /private/approved-model-shards
```

Then run actual backend generation if local llama.cpp and the model are available:

```bash
python -m skeleton.ai.runtime.operational_ai.transport.gguf_cli smoke \
  --root /private/approved-model-shards --context 2048 --threads 4
```

Only an observed `native-generation-observed` receipt from this real invocation
qualifies as a live local inference smoke. A fake-loader unit test, packaging
integrity or source compilation does **not** qualify it.

### Private persistent offline chat

Create a 32-byte cryptographically random master key outside Git and make its
permissions 0600, with a private parent directory and no symlinks. Do **not**
commit the key, put it in a model prompt, log it or paste it into CI. Keep an
off-device recovery copy under the operator's approved key custody procedure.
An unavailable/lost key makes the encrypted memory unreadable; the system will
fail closed rather than silently losing tenant separation.

```bash
python -m skeleton.ai.runtime.operational_ai.transport.gguf_chat \
  --model-root /private/approved-model-shards \
  --memory-key-file /private/keys/ai-memory.master \
  --state-dir /private/ai-state \
  --message 'Explain your local capabilities' \
  --context-tokens 2048 --max-new-tokens 128
```

The CLI returns a generated text receipt, model hash, token counts and durable
conversation ID. Reuse `--session` to continue; supply stable request IDs for
idempotent retries. The model cannot call tools automatically: tool execution
requires an independent caller-issued grant with a pinned schema digest and an
explicit risk ceiling. All chats stay in the canonical existing
`OfflineChatStore`; the new optional operation ledger is not a second chat
truth. State and sealed memories are separate private SQLite stores.

For a private server, provide a random bearer credential through the designated
operator secret entry point and call the same CLI with `--serve` and
`--port 8765`; only literal `127.0.0.1` is admitted. No CORS or remote bind.
`transport/live` adds paged, HMAC-bound replay of committed audit events; it
is not a fabricated low-latency token stream.

### Build the complete 1.9 GB ordered artifact

The previously committed `scripts/build_ai_ecosystem_bundle.py` accepts the
approved model shard folder and its `approved_artifacts.json` ledger. Run it
outside the repository, setting its bundle output to an external private path.
It checks all canonical tracked source files and approved payload bytes in
MBW-00 through MBW-07 order, refuses unclassified additions, verifies SHA-256,
checks actual target archive bytes and never commits or fabricates binary
weights. Output target is 1,900,000,000 decimal bytes, within its strict
published 1,880,000,000–1,920,000,000 byte window.

**Dependency:** The installed checkpoint must have the appropriate real size.
A small native test fixture will not satisfy the 1.9 GB byte threshold.

## Failure behavior

- Missing or unlicensed model -> no activation.
- A symlinked shard, modified shard bytes, unsupported GGUF header, duplicate
  manifest path, or mismatched total SHA -> no activation.
- Group-/world-writable operator model directories -> refused.
- Failed sealing or inadequate memory headroom -> refused.
- Missing llama-cpp binding -> refused; never return fake successful text.
- Model/session/tokenizer identity drift -> refused by the existing gateway.
- Prompt-injection-like instructions inside a source -> untrusted reference
  quarantine; never receive system/tool authority.
- Retrieval source revision change -> old citations no longer verify.
- Missing memory approval, wrong key, wrong scope, tampered AEAD tag -> denied.
- Model tool proposal without separately authenticated caller grant -> denied.
- Stale work lease or duplicate conflicting request -> denied; no auto-retry
  of side effects with unknown external finality.
- Outbox retry exhaustion -> dead-letter/incident, not silent success.
- Corrupt journal chain/snapshot anchor -> recovery held for operator review.
- Missing required exact-head CI or device evidence -> release refused.

## Evidence that is *not* established by the source implementation

The focused tests exercise code contracts and test-only fixtures. They cannot
establish real model intelligence, multilingual quality, usable long-context
capacity, offline cold-start latency, target laptop memory/thermal behavior,
metal/DirectML GPU support, complete distributed security, deployable Windows
installer, trained weights, real 1.9 GB archive, or release readiness. Those
require real installed payloads, observed device runs and independent, exact
head verification. The current PR must stay draft until these gates complete.

## Focused verification on the complete source tree

```bash
python -m unittest discover -s skeleton/testing -p 'test_ai_10x_*.py' -v
python -m unittest skeleton.testing.test_operational_ai -v
python scripts/check_ai_file_tree.py
python scripts/check_ai_master_build_sequence.py
python scripts/check_artifact_policy.py --help
```

For the real native transformer acceptance, run the existing test
`python -m unittest skeleton.testing.test_operational_ai_native -v` in the full
Skeleton checkout with its canonical native transformer modules. The isolated
focused-fixture environment used for this build is not a substitute.

Stage all newly changed files under the same exact GitHub PR head; run the
mandatory security/CI gates against that exact resulting SHA before promotion.
Do not count a skipped, pending, cancelled, failed or superseded check as a pass.
