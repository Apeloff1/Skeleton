# Dragon cross-session navigation and local Jeeves discourse

## Authority and operation

The canonical CrawlRun remains the sole network dispatcher. Federation is
locator metadata, not reviewed knowledge, a remote-access grant or source
body retention. Parser and per-run bounds remain finite. The execution
snapshot still enforces consent, host policy, robots, pacing and trap circuits.

### Cross-session federation

1. Finish or exhaust an authorized companion capture.
2. Read its current navigation inventory and checkpoint digest.
3. POST `/api/dragon-academy/crawler/sessions/{id}/navigation/federate`
   with `expected_snapshot_digest`, a separately justified `rights_reference`,
   `retention_seconds` (900–315360000), and `acknowledged: true`.
   This explicitly grants retention of public locator metadata independent
   of the transient capture grant. It does not grant a future request.
4. GET `/api/dragon-academy/crawler/navigation/federation?query=flight%20manual`
   for keyset-paginated current metadata across retained sessions.
5. DELETE `/api/dragon-academy/crawler/navigation/federation/{grant}` to revoke.
   POST `/api/dragon-academy/crawler/navigation/federation/purge` in bounded
   batches to erase inactive metadata. Revoking capture/session consent does
   not implicitly revoke an independently granted retention receipt.
   Revoke that receipt explicitly to remove access to its metadata.

The catalogue uses existing configured owner-sharded GameCorpus SQLite
storage. Records are deduplicated by exact public HTTPS target identity.
Each source checkpoint has its own witness: multi-session occurrences remain
independently revocable. Query-bearing/unsupported URL shapes are excluded
from durable federation (even if permissible in a transient session).
There is no new fixed global target count, but actual disk, SQLite and
deployment limits and reserves apply. No automatic retention is enabled.

### Live local dialogue

GET `/api/dragon-academy/crawler/sessions/{id}/navigation/packet` while its
manual companion frontier has a ready candidate and no pending dispatch.
The packet contains bounded objective/path terms and opaque candidate IDs,
not source body text, URL queries or credentials. It is valid for fifteen
minutes, for the same checkpoint, and only for one target selection.

Send the JSON packet response to the authenticated running local-only Jeeves
application, using the existing operator's token file, for example:

```sh
python scripts/dragon_local_navigation_discourse.py --port 8765 \
  --token-file /private/path/jeeves-token --approve-local-inference < packet.json
```

The actual port is the one printed by the local service. Save the returned
advice object (not the whole role receipt) in the existing manual run command
as `navigation_advice` with the packet's session version. A stale packet,
foreign candidate, malformed model output or unavailable local model cannot
authorize any dispatch. Rebuild the packet if rejected. The existing local
inference store retains the two role conversations and execution receipts;
the operator may delete these using ordinary local conversation controls.

The same primary local model executes two separate role contexts per match.
The 48-candidate stratified tournament uses up to nine two-role matches (18
actual inference calls), groups of at most eight candidates, and a final
rank. A missing or invalid local response aborts the entire advisory result. Dragon
critiques the first Jeeves ranking. This is genuine two-call orchestration
when executed, not two separately trained models or a new model checkpoint.
Rank influence is bounded and remains inactive during recovery/conservation.
The backend treats imported advice as untrusted advisory data, not as proof
of native execution. It cannot verify a receipt from a different machine's
local SQLite store. Deterministic browsing still works without this step.

## Qualification

The exact-head workflow runs canonical navigation and host-backpressure tests,
and physical SQLite fixture writes/read-back across 160 sessions (20480 matches).
For a larger controlled scratch run, set
`SKL_DRAGON_NAV_QUALIFICATION_BATCHES` between 40 and 4096 and run
`PYTHONPATH=.:backend:tests python -m unittest discover -s backend/tests -p test_dragon_navigation_federation.py -v`.
The test reports measured rows/second, bytes, integrity check and read-back.
It does not qualify the end user's device, distributed storage, production
failure recovery, real internet acquisition or two independently trained models.
Existing code-bound snapshots need separately authorized upgrade/migration;
do not rewrite their integrity receipts to force admission.


## Wide graph and adaptive browsing

The checkpoint inventory holds up to 4096 records subject to its 1 MiB
conservative byte envelope; incremental accounting is independently
recomputed on restore. Supported document paths now request up to 1024
links and structured parsers examine up to 4096 entries. Protocol-specific
limits, snapshot limits, active frontier capacity and response-byte limits
remain separate; this is not exhaustive extraction.

New owner-scoped endpoints under `/api/dragon-academy/crawler/navigation/federation`:

- POST `/batch`: specify 1–16 exact session/checkpoint pairs, independent
  retention duration and rights acknowledgment. Each grant is transactional
  and replay-safe; a batch may have mixed held/published outcomes.
- GET `/shortlist?query=...`: indexed exact lexical, concept and trigram
  candidate lanes; optional host and due-only filter. Up to 48 proposals.
- GET `/portfolio?query=...`: advisory Jeeves objective score and Dragon
  novelty, host-diversity, lineage and historical-outcome score with marginal
  redundancy suppression. Up to 24 proposals.
- GET `/targets/{sha256}/topology`: active grant-scoped parent or child edges.
- GET `/targets/{sha256}/trail?query=...`: cycle-safe directed browsing trail,
  up to six hops and 48 proposals. An edge is an observed historical link,
  not proof that the destination is safe, current, or still exists.
- POST `/targets/{sha256}/review`: optimistic revision compare-and-set on
  candidate/held/retired classification and next review time.
- POST `/reindex`: explicitly rebuild old or missing semantic postings in
  keyset batches. This cannot invent historical topology absent from older
  retention grants.

All routes preserve owner scope, no-network authority, separate retention
rights and grant expiry. New publications atomically retain witnessed
topology, metadata-only outcome classifications and versioned posting lanes.
The existing exhaustive keyset FTS listing remains separate from the bounded
approximate research portfolio. Index migration, incomplete lanes and
incomplete topology are reported. No actual capture is automatically launched.

The physical fixture qualification validates grant/nodes/edges/postings/
outcome counts and SQLite integrity/readback; live native model tournament,
user hardware, and production throughput require separate evidence.


## Intelligent research planning and archive processing

POST `/api/dragon-academy/crawler/navigation/federation/research-plan` with
`query`, `budget` (1–48 advisory units), `mode` (balanced, coverage,
exploration, conservation), and optional prior target IDs (up to 128).
The planner decomposes objectives into up to eight search facets and
samples rotating owner/query/epoch-specific index windows. Jeeves scores
estimated marginal objective coverage, historical yield and lineage;
Dragon scores uncertainty, novelty and source diversity. Both proposals
are reconciled against estimated work cost and redundant term overlap.
Receipts identify omissions and incomplete indexing. Estimates are not
measured probabilities of future acquisition success or transport budgets.

GET `/api/dragon-academy/crawler/companion/archive-intelligence?session_id=...`
with optional `compare_session` for exact payload groups, estimated duplicate
bytes, content-defined chunk reuse, sampled shingle similarity and changes
in matched canonical URL families. Only currently granted historical
sources participate. Both session versions, grants and source policies
are rechecked before returning derived metadata. No raw text, deletion,
physical compaction, training authority or live browsing is performed.

The leased deep archive index worker builds its lexical, rare-term and
passage routes through one permission-verified source pass, with the
same output formats and digest semantics. Deep search and historical
context reuse bounded exact-content computations inside one user
operation, not persistent cross-user caches. Source authority, immutable
text witnesses and exact passage checks are still independently enforced.
Weighted feature accounting is conservative rather than measured RSS.

Qualification tests compare all three existing route objects and exact,
hybrid and passage scores, exercise expiry, revocation and checksum drift,
and verify planner budget/exclusion and owner boundaries. Real-device
throughput, production archive scale, actual physical chunk compaction,
autonomous model discourse and separately trained role models remain
independent qualification or implementation work.


## Autonomous Jeeves–Dragon discourse

The finite crawler execution grant accepts optional
`navigation_discourse: true` with an explicit enabled companion session.
This is not a new acquisition grant. The existing owner/editor role,
consent, automation epoch, slice quota, origin stripes and live transport
checks still govern each dispatch. An opted-in grant uses one canonical
slice step per pulse. Before a new model-ranked selection it reserves a
bounded advisor window with the existing row/version compare-and-set.

Configure `SKL_DRAGON_AUTONOMOUS_DISCOURSE_JSON` on the backend with exactly
`owner_digest` (navigation_semantics.digest of the tenant_id/owner_id scope
object), `port` (the running local-only Jeeves HTTP port), `token_file`
(an absolute owner-private token file), and `model_digest` (the exact
configured local model digest). The connection is always 127.0.0.1;
the user cannot supply a destination, credential or arbitrary inference
parameters. A 180-second advisor deadline is further narrowed by the
original grant. The local HTTP service serializes tournaments and
checks the supplied deadline before every role. Invalid or unavailable
advice holds an opted-in new selection instead of silently falling back.
An already reserved interrupted dispatch or an empty candidate packet is
handled by the canonical runner without a new model selection.
The completed run receipt records model identity, actual role count and
the exact returned receipt digests. This binds the trusted local service
response; it is not remote hardware attestation. Roles still use one
primary model, not independently trained weight sets.

## Physical compressed chunk compaction

New explicitly authorized Hoarder bulk copies now use bounded content-
defined byte chunking (32 KiB minimum, approximately 64 KiB target,
256 KiB maximum), compressed physical chunk storage, exact SHA-256 keyed
reuse and independently witnessed manifest placement. The layout itself
has a digest and is written transactionally with the manifest. The
existing append/seal/abort/collect protocol is unchanged in authority:
a complete reconstruction must match the original byte count and hash.
An existing fixed-layout manifest replays in its original format.
No old copy is destructively migrated; cold-primary manifests still use
their existing fixed-format reader. Offline copied-ecosystem audits
recognize both layout types and verify the entire reconstructed payload.

Deduplication shares storage only within the same existing owner and
physical manifest-write namespace. Logical compressed storage savings do
not necessarily imply immediate file shrinkage or secure erasure of
SQLite pages, WAL or backups.

## Learned semantic optimization

The research-plan request accepts optional `learned: true`.
A configured pinned local ONNX encoder reranks a bounded pool using
objective and public locator path terms only, with exact batch dimensions
and finite normalized vectors. An unavailable encoder is reported as
held rather than claimed as measured inference. A transient regularized
logistic fit uses active-grant operational outcome counts (not source
bodies); immutable target hashes split training from holdout. It influences
ranking only when held-out log loss improves on the empirical prior.
The learned state is not persisted or shared across owners, and the
source's no-training flag is unchanged. Concurrent catalogue changes or
expiry hold the result. This is operational calibration, not a benchmark
of general factual or semantic quality.

## Measured storage qualification

The exact-head workflow runs the focused archive/crawler suites and
physical fixed-vs-content-defined fixture qualification on the CI device.
For a larger real scratch workload under a dedicated writable directory:

```sh
PYTHONPATH=.:backend python -m core.dragon_chunk_qualification \
  --scratch-directory /absolute/private/scratch \
  --families 128 --revisions 4 --size 1048576 \
  --acknowledge-scratch-writes
```

The command compares real compressed payload and database bytes, writes
and reconstructs all fixture revisions after reopening the manifests,
runs SQLite integrity and WAL checkpoint checks, and verifies
reference-aware cleanup. Its bounded aggregate cap is 4 GiB of logical
fixture input across both layouts; sufficient disk reserve is required.
For actual configured storage devices, use the existing separately
authorized `core.dragon_capacity_qualification` scratch probe and the
existing copied-ecosystem sealed-payload audit. These are intentionally
not production-load, physical maximum capacity, power-loss or launch
qualification. No user-device, live native tournament or real encoder
model performance is asserted by fixture tests.


## Existing sealed archive migration

Owner-scoped GET `/crawler/companion/bulk-migration-candidates` returns
keyset pages of eligible copy markers (not layout attestations).
POST `/crawler/sessions/{session_id}/migrate-bulk-copy` uses the
existing expected_version, idempotency_key and retention_acknowledged
contract. POST `/crawler/companion/migrate-bulk-batch` accepts up to
eight explicit session/version/key objects and retention acknowledgment.
Results are independent and may be held. The immutable original
manifest ID is the replay identity; a fresh idempotency key does not
create an additional copy or extend retention.

The migration recomputes current grant-bound exact source bytes and
checks the existing manifest hash and length. A deterministic staging
manifest in the original owner write lane is journaled before any
physical write. The staged content-defined layout is sealed and both
old and new layouts read back under one ledger fence. A SQLite
transaction switches placements and retires the staging manifest while
preserving the original identity. Old chunks become collectible only
after the switch, and if no live manifest references them. A crash
before switch leaves the original readable; replay resumes staging.
Original deletion fences staging and transfers garbage obligations to
its tombstone. The data representation changes, not the capture,
authority, canonical Mongo primary or independent backup rights.
Previously unqualified historical checkpoints remain held. Cold
primary and independent backup migrations are separate operations and
are not automatically authorized by this bulk-copy command.

## Independently trained Dragon specialist

`skeleton/ai/webcrawler/models/dragon_navigation_ranker.v1.json` is an
actual 10-input, 16-hidden-unit, one-output neural ranker with 193
learned parameters. The dependency-free original synthetic curriculum
in `scripts/train_dragon_navigation_ranker.mjs` trains on 8192 examples,
holds out 2048 independent examples, and performs 32 epochs.
Measured synthetic holdout accuracy: 0.9233398438; log loss:
0.1609377581 against the fixed semantic baseline 0.6038829698.
No external capture bodies were used. The artifact is not a second
generative LLM, a general-world quality benchmark or proof of training
on production outcomes. CI reproduces training and checks all weights
and recorded metrics within a floating-point tolerance.

For the separate learned Dragon role, configure the local Jeeves service
with `SKL_DRAGON_SPECIALIST_JSON` containing exactly `path` (canonical
absolute path to the JSON weight artifact) and `sha256` (SHA-256 of
its exact bytes). Add that same `dragon_model_digest` to the existing
owner-pinned autonomous inference config. The model identities are
bound inside the finite execution grant; changing either requires a
new grant. The HTTP tournament uses real native Jeeves inference for
Jeeves and independent numeric specialist inference for Dragon.
The specialist emits distinct execution receipts with model identity,
feature and packet digests, and output ranking digest. It does not
assert a native SQLite generative receipt. No primary model policy,
network authority or source training permission changes.

Manual verification: use `scripts/dragon_local_navigation_discourse.py`
with the existing approved packet input, `--jeeves-model-sha256` and
`--dragon-model-sha256` in addition to the local port and token file.
The command fails closed if the independent role was not exercised.

## Live and hardware qualification

On an operator-controlled machine with the exact clean source checkout,
configured private storage volumes, and a running local native Jeeves
service (with its separate Dragon specialist pin), run
`PYTHONPATH=.:backend python -m scripts.dragon_live_device_qualification --help`
for the explicit options. Supply the exact Git head, both model digests,
loopback port, private bearer token file, explicit permission for local
inference and private scratch writes, and minimum NDCG and read/write
rates plus maximum p95 latency. The tool exercises synthetic navigation
tasks against the actual local service, refuses replayed receipts,
measures configured-device scratch I/O and actual compressed archive
write/readback benchmarks, revalidates device inventory, and binds all
results to the clean source head. It does not touch production traffic
or claim independent physical attestation, power-loss tolerance,
maximum sustained capacity or launch certification. The hosted CI
source tests can exercise real trained specialist arithmetic and
disk-backed test migrations, but not the operator's native GGUF model
or installed production hardware.


## Seventh expansion: ensemble planning and higher-throughput archival custody

The independent Dragon v2 artifact retains v1 compatibility and has three
32-hidden-unit pairwise neural rankers (1,152 learned parameters versus
193). The original grouped synthetic training script processes 3,072
eight-candidate groups (24,576 candidate examples), with 512 development
groups and 1,024 shifted holdout groups (8,192 candidate examples).
On the same shifted holdout, comparison with the v1 specialist and lexical
baseline is recorded in the weight artifact:

| Model | NDCG@3 | Pairwise accuracy | Top-choice regret |
| --- | ---: | ---: | ---: |
| v1 | 0.983286 | 0.942451 | 0.040619 |
| v2 | 0.989791 | 0.970524 | 0.026193 |
| lexical | 0.940041 | 0.906172 | 0.183707 |

These are measured original synthetic ranking results, not general-world
relevance or live LLM qualification. Select the new operator-pinned v2
artifact in the existing specialist configuration. The runtime evaluates
ensemble disagreement, then uses a 12-wide four-step beam with at most
384 numeric feature evaluations per group. Equivalent membership states
share calculations; novel lexical/concept coverage and overlap affect
the recommendation. This bounded planner remains advisory. The tracked
training metrics evaluate the trained scoring ensemble, not the new beam
planner on real traffic. A separate exact-head workflow reproduces the
training and verifies weights and metrics.

Batch payload I/O now uses up to 128 chunks and a 16 MiB aggregate
ceiling per transaction batch. One journal intent is established before
volume publication, existing payloads are independently decoded rather
than recompressed, and duplicate hashes in the batch are written once.
Volume transactions and the final ledger receipt remain recoverable by
exact replay after partial cross-volume completion. Owner partition
namespaces remain mandatory. The coherent document reader holds one
layout and garbage-collection fence for exact whole-document readback;
legacy individual chunk readers remain compatible. No throughput
improvement is asserted until measured on a real workload.

POST `/crawler/sessions/{session_id}/compact-cold-primary` accepts
expected_version, idempotency_key and explicit acknowledged=true with
the existing cold migration feature enabled. It independently admits
both configured stores and the existing qualification receipt, verifies
exact current archive rights and byte identity, converts the backup
first, reads it back, then converts the primary and rechecks both.
A mixed-layout pair is recoverably readable after interruption; no
cross-database atomicity or independent hardware evidence is inferred.
The original Mongo authority, expiry and manifest identities remain
unchanged. An operator must explicitly execute this command on the
deployed environment; the source changes do not migrate any archive.

The live qualification harness now uses twelve curated synthetic task
families, lexical distractors, position variation and independent
relevance labels. The previous label-derived semantic feature was
removed; inputs use the actual semantic feature extractor without
access to evaluation labels. Worst-case task NDCG is reported alongside
aggregate NDCG and latency. Separate CI runs the trained specialist,
real batch fixture recovery, two-store mixed-layout recovery and
reproducible retraining, without pretending to operate your native
Jeeves model or production hardware.
