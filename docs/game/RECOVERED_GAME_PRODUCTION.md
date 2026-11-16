# Recovered asset and multiplayer production paths

Archived source observations identified the existing canonical asset
manifest/import pipeline, headless server, replication and transport
owners, profiler and authored dialogue session. These are composed
without copying archived implementation over current files.

## Source-qualified asset intake

`python -m skeleton asset-source-audit inventory --root assets --asset mesh.obj --asset texture.png --trusted-local-operator`

The explicit supported asset paths are imported through the canonical
descriptor-anchored pipeline. The manifest is restored and reconciled,
then every resolved external sidecar path is admitted under aggregate
bounds and hashed into the source catalog. Aliases resolve their own
sidecars, and content identity and reference paths remain distinct.
For the next observation, select the verify action and independently
retain the earlier catalog SHA-256 as --expected-catalog-sha256.
This is sequential evidence for the supplied inputs, not a directory
snapshot, source publication, license, or native import.

## Headless multiplayer replay and profiling

`python -m skeleton netcode-replay-qualify --ticks 120 --clients 4 --entities 12 --trusted-local-operator`

Runs two independent actual in-memory server/codec/replica simulations
with seeded snapshot loss, duplication and delay. A finite reliable
recovery tail tests convergence, input/ack messages run through the
same framing path, and the complete deterministic transcript and
server-source manifest digest are retained. A separate measured
tick profile uses the canonical FrameSampler; optional hitch limit
can fail local qualification. The deterministic digest deliberately
excludes nondeterministic wall-clock timings. Work bounds protect
the harness, not the general-purpose server or arbitrary transports.
No physical network, sockets, GPU, real game client, native engine,
or release qualification is claimed.

The authored dialogue CLI is also reachable from the installed root
with its original source/save/choice/verification arguments. Existing
canonical owner authority and source contracts are preserved. Fixtures
cover real source parsing and in-memory protocol execution, with
additive selection in the existing qualification gate. Test execution
and hardware evidence remain outstanding.
