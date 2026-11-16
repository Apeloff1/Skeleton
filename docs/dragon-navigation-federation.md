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
not source body text, URL queries or credentials. It is valid for five
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

The same primary local model executes two separate role contexts. Dragon
critiques the first Jeeves ranking. This is genuine two-call orchestration
when executed, not two separately trained models or a new model checkpoint.
Rank influence is bounded and remains inactive during recovery/conservation.
The backend treats imported advice as untrusted advisory data, not as proof
of native execution. It cannot verify a receipt from a different machine's
local SQLite store. Deterministic browsing still works without this step.

## Qualification

The exact-head workflow runs canonical navigation and host-backpressure tests,
and physical SQLite fixture writes/read-back across 40 sessions (5120 matches).
For a larger controlled scratch run, set
`SKL_DRAGON_NAV_QUALIFICATION_BATCHES` between 40 and 4096 and run
`PYTHONPATH=.:backend:tests python -m unittest discover -s backend/tests -p test_dragon_navigation_federation.py -v`.
The test reports measured rows/second, bytes, integrity check and read-back.
It does not qualify the end user's device, distributed storage, production
failure recovery, real internet acquisition or two independently trained models.
Existing code-bound snapshots need separately authorized upgrade/migration;
do not rewrite their integrity receipts to force admission.
