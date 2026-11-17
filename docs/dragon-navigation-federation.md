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
