# Local reference provenance

Reference lookup and learning record pointers, never copied page text. The
canonical implementation remains in `skeleton/cortex`; its local observation
state is declared in `machine/state_topology.json`. It does not grant model,
memory, provider or user authorization.

## Storage and caller binding

Runtime observations go to `<workspace>/.skeleton/references/provenance.jsonl`.
The current directory is the default workspace. Resolving a path or reading a
missing log creates nothing. The packaged `skeleton/acquired/gaming` corpus is
read-only historical reference data and is no longer the runtime log target.

```python
from pathlib import Path
from skeleton.cortex.refs import refer, read_provenance, reference_scope

workspace = Path("/trusted/workspace")
receipt = refer("like Elden Ring", root=workspace)
records = read_provenance(workspace)

with reference_scope(workspace):
    # All nested reference operations, including model learning, use this root.
    refer("Hades")
```

Scopes are context-local, nest correctly, and restore the previous root even
after exceptions. Explicit roots override a scope. They must come from trusted
application configuration, not model output or request metadata. The scope is
not a filesystem sandbox; its parent directories are caller-owned.

`GameRefPort(root=workspace)` binds an explicit root. A restored port accepts a
root from its caller; snapshot data cannot choose a filesystem destination.
Deck speak and plan operations scope their nested work to the deck's root,
including calls through a shared model, without mutating that shared model.

## Integrity and failure behavior

Records retain the existing seven pointer fields and SHA-256 representation.
The writer checks the house laws and scalar/length limits before opening state,
then writes one bounded record and flushes it with `fsync`. Process-local locking
serializes threads. Assign each journal one process owner; this implementation
does not provide distributed or multi-process journal coordination.

The reader verifies the entire selected log before returning records. It rejects
duplicate/unknown fields, invalid scalar types, malformed UTF-8 or JSON, checksum
mismatches and incomplete lines. Errors identify the record number without
including its contents. A missing log returns an empty list; permission and
other I/O errors propagate. Symlink and non-regular journal leaves are rejected.

Each encoded record is limited to 16 KiB and each active log to 8 MiB. Reads
default to 10,000 records; callers may set a bound from 1 to 100,000, still subject
to the byte limits. Reads are bounded even if the file grows after its initial
size check. Full logs require an explicit operator archive; no history is
silently dropped or truncated.

A short write or flush failure never returns a successful receipt. The outcome
may be uncertain: a complete record can exist after a flush error. Inspect the
journal before retrying; there is no automatic retry or deduplication. An
incomplete tail is retained and blocks further appends. Preserve that evidence
and restore a verified backup or explicitly archive the damaged journal before
resuming. SHA-256 is an integrity checksum, not a signature or authenticity proof.

## Validation and rollback

`skeleton/testing/test_reference_provenance.py` covers default/explicit roots,
nested and concurrent scopes, real threaded appends, port restoration, deck
propagation, malformed state, limits and injected I/O failures. The legacy
reference tests continue to verify real temporary records and unchanged corpus
bytes. Run these tests plus the state-topology and governed-tree validators.

No historical log is automatically imported or migrated. Revert the canonical
files, governed mirrors and mapping identities together if needed. Preserve new
workspace journals separately before reverting; old readers will not discover
their new location. Never copy runtime observations into the packaged corpus to
make a rollback appear transparent.
