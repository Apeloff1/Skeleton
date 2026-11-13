# Integral AI boot, model installation and recovery

**Scope:** Operational inference system, not game creation. This is an
additive, fail-closed path through the existing canonical AI tree. It does not
replace `NativeChatEngine` or create a second model authority.

## Dependency order and concrete boundaries

The `MBW-00` through `MBW-07` contract remains authoritative. The executable
AI spine is:

1. **MBW-00 / authority:** bounded model/owner identities, strict request JSON,
   explicit budgets and independently issued grants.
2. **MBW-01 / persistence:** authoritative existing SQLite chat commits,
   idempotent request IDs, hash-chained companion audit and explicit recovery.
3. **MBW-02 / model:** operator-approved local GGUF weights and tokenizer
   metadata, verified per-shard digests, bounded Linux sealed memory assembly,
   real `llama-cpp-python` execution, no provider fallback.
4. **MBW-03 / actions:** model text is untrusted; tool invocation must originate
   from a separately granted caller, and write/effect tools stay held.
5. **MBW-04 / orchestration:** same-session process-local and POSIX
   cross-process locks, followed by a durable SQLite revision fence. Retry
   after committed turn returns its receipt, not another inference.
6. **MBW-05 / API:** authenticated loopback-only HTTP/CLI, no implicit external
   callback, web origin or public host binding.
7. **MBW-06 / evaluation:** explicit regression/adversarial/quality results
   before any model can be called production-qualified.
8. **MBW-07 / install:** one-pass streaming verification and no-clobber
   installation of the real model from the ordered ecosystem artifact.

## A genuine GGUF distribution path

The external operator supplies a real, legally approved and GGUF-compatible
checkpoint. This procedure never fabricates model bytes, downloads weights or
places binaries in Git. Use an existing **private** directory outside the repo
for all artifacts, and treat the license/rights declaration as an independent
operator responsibility. A local integrity hash is not a signature.

```bash
# 1. Prepare a real GGUF into <=99 MB shards, complete model manifest,
#    and `approved_artifacts.json` with byte-accurate model paths.
python -m skeleton.ai.runtime.operational_ai.model.gguf.prepare_cli \
  --input /private/checkpoints/original.gguf \
  --output-dir /private/payload/original \
  --model-id original \
  --license 'OPERATOR_VERIFIED_LICENSE' \
  --source 'operator:independently-verified-checkpoint' \
  --rights-approved

# 2. Build a source-tree-bound, stage-ordered 1.9 GB TAR outside the repo.
#    It is a HOLD if no real model/dataset is available to fill its byte window.
python scripts/build_ai_ecosystem_bundle.py build \
  --repo-root . \
  --payload-root /private/payload/original \
  --artifact-ledger approved_artifacts.json \
  --output /private/distribution/skeleton-ai-ecosystem.tar

# 3. Install the selected model from that actual 1.9 GB archive.
#    `/private/models` must already exist with mode 0700.
python -m skeleton.ai.runtime.operational_ai.deployment.install.cli install \
  --archive /private/distribution/skeleton-ai-ecosystem.tar \
  --install-root /private/models \
  --model-id original \
  --install-id original-v1

# 4. Hash every installed GGUF shard without loading a model or altering state.
python -m skeleton.ai.runtime.operational_ai.deployment.install.cli doctor \
  --model-root /private/models/original-v1

# 5. Provision private state and a local OS-CSPRNG 256-bit key exactly once.
#    These parent directories must already exist with mode 0700; this is
#    explicit operator action and the key is never printed or overwritten.
python -m skeleton.ai.runtime.operational_ai.deployment.bootstrap.cli \
  --state-parent /private --state-name ai-state \
  --key-parent /private/keys --key-name memory.key

# 6. Run real local inference with the private state and key.
python -m skeleton.ai.runtime.operational_ai.transport.gguf_chat \
  --model-root /private/models/original-v1 \
  --state-dir /private/ai-state \
  --memory-key-file /private/keys/memory.key \
  --tenant local --user operator \
  --message 'Explain which local model you are running.'
```

**Note:** The 1.9 GB archive is a distribution object, not a source-Git blob.
It requires 1.88–1.92 GB actual uncompressed archive bytes and at least 1.85 GB
of actual source/artifact content. Individual model shards remain below 99 MB.
The archive includes `models/<model_id>/model.manifest.json` and
`models/<model_id>/weights/...`, the exact structure accepted by the installer.
If your model or other approved assets cannot meet the genuine size floor,
packaging correctly fails; never add padding or forged model bytes.

Successful model installation writes a private, canonical `install.receipt.json`
next to the installed model. The read-only doctor validates installed model
bytes, manifest digest, receipt structure and declared destination, and
preserves the source commit and archive digest from the completed installation.
It **does not independently rehash the original archive** (which may no longer
be available), cryptographically authenticate the signer, or validate rights.
Missing or internally conflicting receipts mean **HOLD**.

## Audit split-commit failure and recovery

`OfflineChatStore` commits the user and assistant turns transactionally. Its
companion audit journal uses a different SQLite database and cannot be atomically
committed by the same transaction. A crash can leave a **committed chat turn**
with **no journal event**. A second model generation is the wrong repair.

The recovery verifier reads committed request fingerprints, output digests,
model identity and revisions from the authoritative chat store. It verifies
every hash-chained journal record, refuses any contradictory or phantom events,
and reports missing audit records **without inference**.

```bash
# Diagnosis: no repair and no live model load.
python -m skeleton.ai.runtime.operational_ai.deployment.install.cli reconcile-audit \
  --model-root /private/models/original-v1 \
  --state-dir /private/ai-state \
  --session ORIGINAL_SESSION_ID --tenant local --user operator --dry-run

# Explicit operator decision only, no model output can grant this action.
python -m skeleton.ai.runtime.operational_ai.deployment.install.cli reconcile-audit \
  --model-root /private/models/original-v1 \
  --state-dir /private/ai-state \
  --session ORIGINAL_SESSION_ID --tenant local --user operator --approve
```

Reconciliation is bounded, idempotent and rejects missing chat history,
malformed request IDs, mismatched digests, tampered event chains or unapproved
repair. It does **not** reconstruct missing model output or authorize tools.

## Cross-process single-writer operation

The live GGUF CLI configures `ProcessSessionFence` by default in the private
`state/session_locks` directory. The lock files are SHA-256 names with private
permissions, opened relative to a trusted parent directory with no symlink
following. A second process waits only until the configured deadline and then
fails closed. Different sessions can proceed independently. A process exit
releases its OS lock, while the authoritative SQLite revision remains the final
commit fence. This is local POSIX custody, not distributed locking.

## Acceptance and unreleased boundaries

Focused tests under `skeleton/testing/test_ai_integral_*.py` exercise actual
source-bound archive assembly, staged installation, verified file reads,
sealed GGUF assembly, no-clobber handling, symlink/traversal/duplicate/tamper
refusal, cross-process lock contention and audit repair. Small original test
models **are not trained weights** and do not demonstrate answer quality.

Release remains held until real GGUF model loading and generation, tokenizer
compatibility, device memory/latency, clean-machine install and rollback,
full final-head CI/security gates, secret storage and rights are independently
qualified. The operator report is an integrity receipt only.
