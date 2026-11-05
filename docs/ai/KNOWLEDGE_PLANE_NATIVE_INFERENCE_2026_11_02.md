# Source-bound, revisioned local AI knowledge — native execution spine

**Purpose:** Close the missing production integration between approved local
operator documents and real model inference. This is AI infrastructure, not a
game system. It is **not** a model, not a substitute for approved GGUF weights,
and not evidence that a generated answer is true.

## Ownership and ordered architecture

The new `context/knowledge_plane` subtree is native operational AI and maps to
MBW-02 (inference/context/retrieval). The production composition update is in
MBW-07. It imports only the lower-level execution spine contracts and
SpineDatabase. No historical `skeleton/context` mirrors are changed; source
tree parity and ownership remain under `machine/ai_file_tree.json`.

## Operating behavior

1. Operator independently approves a UTF-8 source and verified rights tag.
2. Only Linux/POSIX descriptor-anchored `O_NOFOLLOW` source reads are admitted.
   Source root must be user-owned, mode 0700, with bounded regular unique
   files; symlinked parent components and hardlinked files fail closed.
3. Stored document raw SHA-256 is bound to a normalized (line-ending only)
   UTF-8 projection. Deterministic overlapping chunks retain exact character
   coordinates, passage SHA-256 and the full raw document digest.
4. One SpineDatabase `BEGIN IMMEDIATE` transaction atomically creates an exact
   monotonic revision, indexed chunk rows, a hash-chained mutation event and an
   event in the existing transactional outbox. Revision changes require a
   caller-supplied compare-and-swap value; no model output can approve itself.
5. FTS5 only searches the current approved revision under an exact
   tenant/user/model/tokenizer identity. A tokenized query is bounded and
   escaped before it reaches FTS. No cross-scope result can enter inference.
6. `KnowledgeEvidenceProvider` converts verified document hits into the
   existing source-bound `Evidence` shape. The core context compiler labels
   all excerpts **untrusted**; source instructions do not become authority.
7. Normal serving startup now initializes the knowledge extension in the same
   private SQLite database before presenting a live native model session. No
   Internet embedding service or hidden remote fallback is involved.

## Explicit local operator workflow

Provision a private state directory with its immutable principal/model
binding via the existing boot CLI. The following example uses only *public*
placeholder hashes; replace all values with the actual approved installed
model and tokenizer digests (these must match `state.identity.json`).

```sh
python -m skeleton.ai.runtime.operational_ai.context.knowledge_plane.cli \
  --state-dir /private/ai-state --tenant mytenant --subject myuser \
  --model-sha256 "$MODEL_SHA256" --tokenizer-sha256 "$TOKENIZER_SHA256" \
  ingest --root /private/source-corpus --source notes/approved.md \
  --id approvednotes --title 'Approved notes' --rights operator-authored \
  --kind text/markdown --revision 0 --approve-ingest

python -m skeleton.ai.runtime.operational_ai.context.knowledge_plane.cli \
  --state-dir /private/ai-state --tenant mytenant --subject myuser \
  --model-sha256 "$MODEL_SHA256" --tokenizer-sha256 "$TOKENIZER_SHA256" \
  search --question 'What do the notes establish?' --limit 4
```

Search/list/doctor commands run read-only and refuse unbound state; ingestion
and deletion require explicit independent flags. A conflict, corrupt chunk,
missing outbox event, interrupted source read or unapproved rights tag blocks
the transaction. Deletion removes the source from all live retrieval but does
**not** perform secure physical erasure of historical SQLite revisions; data
retention and archival are separately governed. No background inference occurs.

## Trust and release holds

- This SQLite plane protects against cross-principal application mistakes,
  lost revisions and tampered stored excerpts. It is not a signature/MAC and
  cannot protect against an attacker who controls the same OS user or SQLite
  files. Host/FS access controls and full-disk encryption remain necessary.
- FTS5 ranks lexical passages, not factual truth. Even citation identifiers
  accepted by the core audit do not independently verify generated assertions.
- Bounded doctor reconstructs normalized source text from chunk coverage,
  checks SHA-256 and the complete mutation-event/outbox chain. The FTS query
  index is **not** itself an independent content authenticity authority.
- Live approved GGUF, true end-to-end first-install, clean-device performance,
  final-head CI/security and operating-system hardening are not qualified by
  fixture-backed tests. Retain all draft/merge/release holds.

## Tests and performance contracts

```sh
python -m unittest skeleton.testing.test_ai_knowledge_plane -v
python -m unittest skeleton.testing.test_ai_execution_spine \
    skeleton.testing.test_ai_flight_control -v
python -m compileall -q skeleton/ai/runtime/operational_ai/context/knowledge_plane
```

The budget defaults cap one source at 2 MiB, total retained bytes at 128 MiB,
active documents at 2048, chunks per document at 4096, search terms at 12,
retrieval hits at 6, and full doctor scan at 65,536 stored rows. Quotas are
*enforced*, not estimates. The 1.9 GB ordered model bundle and source file
size policy remain separate; do not put GGUF or generated archives in Git.

## Bulk corpus admission and index repair

The operator can issue `ingest-batch --root ... --manifest approved.json
--approve-ingest`. The manifest is a bounded, strictly parsed JSON source
under the private corpus root; every member contains `source`, `document_id`,
`title`, `rights`, `content_type` and `expected_revision`. At most 16 files
and 64 MiB of input are admitted together, and any failure rolls back all
revisions, FTS entries, audit-chain events and outbox entries. No partial
import can leak into retrieval.

A read-only `doctor` checks SHA-256 of every passage, complete normalized
source chunk coverage, mutation-chain order and transactional outbox custody.
A distinct `check-index` command invokes SQLite FTS5's external-content
integrity check under a short write transaction; `rebuild-index
--approve-rebuild` first validates all canonical source bytes and events, then
atomically recreates the FTS postings from canonical chunks. Rebuild refuses
unapproved action, source corruption, or a concurrent source mutation.

**Startup behavior:** the native GGUF production `activate()` now verifies
source custody and FTS5 postings *before* exposing the inference service.
This is deliberate fail-closed behavior; a corrupt knowledge index blocks
startup until explicitly investigated and repaired. Initial knowledge
registration and source search share the same existing private spine database.

**Revision/forget semantics:** FTS query results exclude both superseded and
forgotten revisions, but historical chunks and mutation events remain for
provenance. This is not a secure-erase implementation. Retention deletion must
be designed separately with backup custody and operator-approved irreversible
purge.

**Crash-boundary semantics:** if an operator revokes or replaces a source while
native generation is in progress, the runtime checks that source again inside
the authoritative turn-commit write transaction. A revoked or modified source
causes a held inference (no durable assistant answer and no automatic rerun).
The source commit is never silently reapproved.

## Exact Git-source provenance (AI self-inspection)

The optional `repository` subpackage indexes operator-approved **Git blob
objects** from an explicit full commit SHA, never the worktree, symlinks,
submodules or untracked files. It is restricted to canonical AI code and
architecture-document prefixes. It rejects secret-like paths and conservatively
recognized credentials in content. It is intentionally not a complete secrets
scanner; independent Secret Scanning remains required.

A Git import is an all-or-none transaction over at most 32 explicitly listed
sources. It stores revision-bound commit SHA, object ID, raw SHA-256, and
canonical corpus document ID in a foreign-key-checked SQLite lineage table.
Future changes to the source require exact revision compare-and-swap. The
operator can independently re-read all the original Git objects and compare
bytes/digests against the knowledge rows without any network call.

Example, after setting real identity digest variables and a private manifest
root:

```sh
python -m skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository.cli \
  --state-dir /private/ai-state --repo-root /private/Skeleton \
  --tenant mytenant --subject myuser \
  --model-sha256 "$MODEL_SHA256" --tokenizer-sha256 "$TOKENIZER_SHA256" \
  ingest --commit "$EXACT_COMMIT_SHA" --manifest-root /private/source-manifests \
  --manifest approved-sources.json --approve-ingest
```

The exact-commit manifest is `skeleton.ai.exact-Git-sources.v1` with fields
`schema`, `commit_sha` and `sources`; each source entry contains `path`,
`expected_revision`, `rights`. Unchanged source content in a different commit
cannot be re-certified by quietly rewriting the original Git provenance.
Use `doctor` on the same CLI for a bounded independent source-object check.

This does not prove source rights or generated-code correctness. Code and
Markdown excerpts remain untrusted model context, not executable instructions.
The helper runs `git cat-file` with bounded timeout/output and without provider,
network, or authentication fallback. Production use still requires verified
model activation, deliberate source approval, isolation, and final-head CI.
