# Operational AI native runtime: identity, admission and real-model readiness

Scope: the **AI model's own runtime** in `skeleton/ai/runtime/operational_ai`.
This pass does not change quest, world, scene, game or artifact-generation
implementations. It closes trust and liveness gaps between verified local
model installation and actual durable inference.

## First-install dependency order

1. **MBW-00 authority and caller identity**: The caller selects an explicit
   tenant and user. `PrincipalBinding` demands bounded ASCII identifiers and
   full-length lowercase model and tokenizer SHA-256 identities; neither the
   model nor a prompt is allowed to select or override them.
2. **MBW-01 private durable state**: Provision a private state directory using
   the existing OS-key bootstrap command. Before chat/memory/audit databases
   are opened, the runtime makes an exclusive, immutable
   `state.identity.json` record. An already populated but unbound directory
   blocks startup. A second principal or model cannot inherit the database.
3. **MBW-02 approved real inference**: Select approved GGUF shards installed
   from the source-bound archive. Read the installer receipt and hash the
   complete installed model. Refuse absent/unsafe `llama_cpp` instead of
   switching providers. Assemble the verified anonymous sealed image and
   invoke real native generation. Tool-call and role-spoofed native completions
   cannot be turned into ordinary assistant output.
4. **MBW-03 tool policy**: The model output is **data**, never tool authority.
   The existing separately granted tools are not exposed as callable native
   backend functions. Fail on attempted tool-call finish reasons.
5. **MBW-04 durable chat**: Same-process lock and cross-process descriptor
   session lock serialize model generation before checking committed receipt
   replay. A conflict cannot safely trigger an unbounded second generation.
6. **MBW-05 private serving**: Only literal loopback host addresses, a strong
   bearer token and an exact Host header are accepted. Browser Origin is
   denied. Ambiguous Transfer-Encoding, duplicate singleton headers and
   `Expect: 100-continue` are rejected. Socket I/O and active connections are
   bounded; unexpected errors are redacted.
7. **MBW-06 independent evaluation**: Live-model smoke emits native token
   counts and a digest, not a quality or release certification. The test
   harness uses fixture backends only to test contracts and errors.
8. **MBW-07 build/qualification**: The PR stays draft until required exact-head
   CI and external install, restore, device, model rights, security and real
   throughput evidence are collected.

## Operator sequence

Securely provision state/key in approved private directories, using the
existing `deployment.bootstrap.cli`. Install an approved GGUF from the ordered
bundle with `deployment.install.cli install`, then bind the state:

```bash
python -m skeleton.ai.runtime.operational_ai.deployment.boot.cli bind \
  --model-root /private/approved-model --state-dir /private/state \
  --tenant local --user operator --approve-new-state

python -m skeleton.ai.runtime.operational_ai.deployment.boot.cli doctor \
  --model-root /private/approved-model --state-dir /private/state \
  --memory-key-file /private/keys/memory.key --tenant local --user operator

python -m skeleton.ai.runtime.operational_ai.model.gguf.probe_cli \
  --model-root /private/approved-model --context-tokens 2048 \
  --new-tokens 16 --threads 4 --gpu-layers 0

python -m skeleton.ai.runtime.operational_ai.transport.gguf_chat \
  --model-root /private/approved-model --state-dir /private/state \
  --memory-key-file /private/keys/memory.key \
  --tenant local --user operator --message 'Hello'
```

For the loopback service, set a secret generated from an independent CSPRNG
(e.g. 32 random base64 characters or more) as
`SKELETON_LOCAL_AI_BEARER`, and replace `--message` with `--serve --port
8765`. Never check the secret into Git, put it in a URL, or print it in logs.

A successful content doctor **does not** mean a working model. A successful
live smoke proves only that a single genuine generation executed. The first
install must still be independently tested across actual supported CPU/GPU
hardware and restart/recovery scenarios; a service with no approved checkpoint
must remain unavailable.

## No implicit upgrades / no fabricated migrations

The first-run binder refuses a directory containing unbound `chat.sqlite`,
`memory.sqlite`, `audit.sqlite`, `session_locks` or sidecar WAL/SHM files.
This may temporarily block existing local development databases. That is an
intentional privacy hold, **not data loss**. Operators must make a separately
approved migration plan that inventories original principal ownership before
copying any conversation state. A new empty state directory is the default
migration-free route.

The state identity file is a checksum-protected owner-private record, not a
cryptographic signature, not an anti-rollback mechanism, and not protection
against a malicious process already running as the same OS user with write
access. OS account separation remains required for adversarial tenants.

The native GGUF adapter intentionally rejects completion functions and tool
calls; such results cannot be silently treated as successful assistant text.
The updated gateway also counts malformed receipts, context/usage overshoots
and identity changes as model-circuit failures, not just thrown backend errors.

## Test evidence and holds

Focused tests exercise private principal custody, wrong-model and wrong-user
refusal, legacy unbound state, symlink and hardlink refusal, corrupted binding,
concurrent first-open, real local HTTP protocol parsing and authorization,
model failure circuits and native loader receipt contracts. Broader existing
GGUF, tool, serving and installer suites are also run locally. They use
original fixture model bytes and do not replace a real GGUF live-model smoke.

Production readiness still requires on-device live-model inference with an
independently approved model, exact-head CI/security review, model licensing,
context budget validation and durable restore testing. None of these are
implicitly passed by committing source files.

## Secondary entrypoints and recovery

The native JSON-checkpoint CLI (`transport.cli`) also uses the exact same
principal/model state binding and cross-process session fence. Its chat,
memory and audit database files must be siblings in one owner-private state
root; scattered storage paths cannot bypass the boundary. As on the GGUF
route, first use of a previously populated, unbound directory intentionally
fails pending independent migration review.

The installed-model audit reconciliation operator CLI (`deployment.install.cli
reconcile-audit`) requires the same `state.identity.json` identity check
before opening any conversation database, even for `--dry-run`. The caller
cannot select a different tenant/user to inspect or backfill somebody else's
stored receipts by changing command-line flags. This is an OS-local boundary,
not protection against untrusted programs already running under the same UID.
