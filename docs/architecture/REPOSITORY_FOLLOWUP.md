# Repository integration follow-up

This continues the combined tree migration in `REPOSITORY_INTEGRATION.md`.
Canonical capability owners and provider boundaries are unchanged.

## Completed repairs

- `skeleton/distributed/network/replication.py` now owns sessions, ordering,
  history, and rollback. `_replication_protocol.py` owns packet types, canonical
  serialization, checksums, and validation. Existing public imports remain
  available from both canonical and compatibility namespaces. Frozen packet
  checksums captured before extraction verify that wire behavior is unchanged.
- `skeleton/organism/paths.py` supplies the missing state, Galaxy, KV, ledger,
  and helix paths required by existing persistence consumers. Helpers resolve
  beneath the existing organism directory and perform no writes themselves.
  The default is `.skeleton/organism/`; an explicit root uses `<root>/organism/`.
- `MeshHandoffAdapter` connects existing agent routing to existing handoff
  envelopes. It selects a healthy capable agent before creating an envelope,
  preventing orphan tasks when no agent can serve the request. The registry
  retains state-transition and event ownership. The adapter executes no task.
- Galaxy HTTP handlers are bound per transport instance. Previously, starting
  another node overwrote the shared handler's transport, breaking remote task
  replies. Repeated start is idempotent, and stop closes the listening socket.
- Source and governed AI mirrors remain synchronized. Merge Readiness now
  exercises replication, path recovery, handoff, and Galaxy bridge contracts.

## Outstanding broader compatibility failures

Expanding beyond the original merge checks exposed failures in
`test_galaxy_brains.py` and `test_organismer_social.py`. These are tracked here;
they are not suppressed, quarantined, or represented as passing:

| Area | Observed mismatch |
| --- | --- |
| Cortex command deck | Older callers pass a model positionally; the current constructor treats it as a filesystem root. |
| Organism diagnostics | Callers provide an organism and `neo`/`fix` arguments to doctor/nervous APIs that now accept only a root. |
| Vault integration | The key registry imports `DataKey` and `EnvelopeKMS`, which are absent from its KMS module. |
| Context loop | The journal loop imports the missing `RotGuardedCompactor`; guarded compaction currently exposes `compact_turns`. |
| Social tests | Historical source-house labels differ from the current `X`/`arXiv` labels. |
| Resource budget tests | The old tiny-tier walk expectation differs from the current bound. |

Resolve these through declared capability contracts and current production
consumers before changing behavior. In particular, do not invent cryptographic
implementations or report preserved memory constraints without evidence.

## Verification and rollback

Run the mandatory architecture/construction/capability/provider validators and
AI-tree parity, then the focused tests listed in Merge Readiness. The replication
suite covers malformed packets, bounded buffers, acknowledgements, atomic failure,
prediction reconciliation, and rollback. Bridge tests use local loopback nodes.

Revert the extraction and its mirrors together. No packet schema or stored
format changes are introduced. Reverting the path helpers restores the prior
missing-import failure and should not delete any subsequently persisted files.
