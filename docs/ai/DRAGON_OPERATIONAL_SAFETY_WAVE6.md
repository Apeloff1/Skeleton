# Dragon Wave Six — Operational Assurance and Recovery Safety

This source-bound implementation adds a *second, six-gate operational plane*
to the 26-stage Dragon Atlas research pipeline and 26-stage forensic chain.
The plane is a deterministic, replay-verifiable **preflight** over the real
`CrawlRun` snapshot and current, authenticated campaign mandate, not an
alternate scheduler or transport.

## Modules

1. `ops_timeline.py`: replay the canonical finite event ring and disclose
   missing prior history, interior gaps, out-of-order clocks, future events,
   pending dispatch and uncertain request/byte reservations without raw URLs
   or untrusted page content.
2. `ops_host_governor.py`: derive per-origin robots observations, cache
   freshness, host retry/cooldown, and queued ready counts. A missing robots
   record can only produce a robots-only preflight candidate, never
   permission to fetch a page.
3. `ops_recovery.py`: bind a typed operator recovery witness to the exact
   snapshot, run sequence and expected worker epoch; require explicit
   worker quiescence, old lease revocation, durable Mongo checkpoint and
   current account/consent claims. Caller booleans are **not** trusted backend
   evidence and never grant dispatch authority.
4. `ops_capacity.py`: narrow the existing canonical budget using bounded
   measurements of RAM, disk, CPU, active fetches, workers and tail latency.
   No measurements means no capacity. Stale, pressure-critical or contradictory
   measurements fail closed, and no original budget is enlarged.
5. `ops_dispatch_envelope.py`: reconcile canonical bounded slice simulation,
   current frontier identity, origin review, restart witness, byte reserves
   and telemetry. Return **opaque URL digests only**, exact snapshot challenge,
   30-second maximum advisory lifetime, and conservative planned costs.
   No worker command, socket, lease, source text or durable reservation exists.
6. `ops_runbook.py`: convert the custody and operational holds into
   deterministic, priority-ordered operator recovery actions. Every action is
   marked unexecuted and requiring real backend authority.

`ops_plane.py` composes these six independent stages into an append-only
hash-linked projection. Verification recomposes the entire source-bound
report, preventing tampered stage order, altered source identity, forged
permission flags, stale clocks, changed operator witness or inflated resource
budgets from being treated as valid.

## Product integration

The existing authenticated `campaign_atlas` backend adapter now builds and
re-verifies this plane before its final Mongo owner/source-policy read. The
response contains only fixed diagnostic counts, digest receipts, bounded
operator action codes, and explicit false authority flags. The Jeeves Atlas
client pins all six stage names and rejects changes to the shape, authority
flags, source snapshot, counters or action codes; the on-screen preflight
section shows the concrete holds and runbook.

Neither the UI nor these modules execute a crawl. The canonical owner
still independently owns current consent, robots, DNS/socket address pinning,
Mongo CAS, durable pre-I/O request and byte reservation, worker lease epoch,
cancellation, and actual recovery.

## Qualification

```sh
python -m compileall -q skeleton/ai/webcrawler/dragon_campaign_stack
python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_ops_wave6.py' -v
python -m unittest discover -s backend/tests -p 'test_dragon_atlas_bridge.py' -v
node frontend/scripts/test-dragon-atlas-contract.cjs
```

These checks do not replace real Windows/WSL2, live HTTP, physical worker
join, Mongo race, security, or device-pressure qualifications. Skipped jobs
remain unverified; failed gates remain release holds.
