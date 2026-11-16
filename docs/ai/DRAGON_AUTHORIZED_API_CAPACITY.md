# Dragon official API, raw entity custody and physical qualification

These features are opt-in operator tools. None is activated by installing the app.

## Official API profiles

The local command `python -m core.dragon_authorized_api --help` supports three
fixed read-only operations: GitHub repository releases, GitHub repository tags
and Hugging Face dataset metadata. It does not run generic authenticated crawling.
Prepare a private canonical JSON grant with schema
`skeleton.dragon.authorized-api-grant.v1`, owner scope, current editor email,
provider, independently authorized resource (`owner/name`), finite Unix expiry,
operation identity, absolute private token-file path, optional raw-store path,
retention seconds, and explicit acknowledgements for publisher permission,
independent resource, egress and retention rights. See `validate_grant` for the
exact field names. Use a narrowly scoped read-only service credential in a
separate private canonical JSON file containing only the token field. Never
commit credentials or put them in command arguments, URLs, or manifests.

Pass the grant's exact SHA-256 and explicit --execute. The command requires an
active original application account database, shared acquisition authority and
direct egress approval. A configured proxy holds this implementation; it does
not fall back to an unapproved path. The transport performs one bounded GET at
the fixed official HTTPS endpoint, does not follow redirects or retry, and
preserves denial signals. An unsuccessful or uncertain request leaves an
owner/host hold requiring independent review. This is not a recovery mechanism
for a denied crawler request. Provider permissions and service terms must be
established separately. Pagination and additional providers remain separate
features.

## Direct entity retention

Retention requires a distinct finite acknowledgement and an already initialized
private raw-export ledger. Only eligible HTTP 200 JSON entities with an
explicit public cache directive, no conflicting private/no-store policy,
sensitive Vary, cookie, partial response, detected instruction concern or
sensitive/ambiguous JSON field can qualify. The response is stored as decoded
entity bytes with exact SHA-256 and owner-bound chunks; transfer framing and
credential headers are not retained. The ordinary crawler still does not
retain arbitrary HTTP bodies. The tool returns metadata, not the raw response.
Neither a successful API call nor retention grants import or training rights.
The operator is responsible for volume encryption, credential protection and
external retention obligations.

## Backup inventory and restored mirror

Use `python -m core.dragon_backup_discovery --help` with an explicit private
canonical root plan, schema `skeleton.dragon.application-root-inventory.v1`.
Supply a stable identifier, declared plane and absolute private path for each
root. Stop all writers, supply the exact plan digest, and write the ledger
outside the scanned roots. Inventory includes files, nested directories,
mode metadata, size and raw SHA-256; it refuses special objects, symlinks,
hard-linked files, overlaps and incomplete traversal. It reports missing
declared planes. The verify-mirror mode compares a separately restored tree
against the exact inventory and rejects missing or extra entries.

This is complete enumeration within declared ordinary-file roots, not proof
that all application roots or external services were declared. It does not
copy the trees or replace the existing application backup coordinator.
Mongo, external services, platform ACLs, extended attributes, encryption keys,
running process state and independent restore acceptance remain separate.
Treat inventory file names and digests as private operational metadata.

## Production-like ingestion measurement

Use `python -m core.dragon_ingestion_qualification --help` with an explicitly
approved private disposable scratch root. The harness runs up to eight
independent canonical LeadGraph stores, at most 250,000 synthetic records per
worker and one million records in aggregate. It executes actual metadata
projection, page commits, FTS insertion, sealing, restart readback, exact page
replay, owner-isolation and SQLite integrity checks. The output reports measured
rows/s, p95 page latency, node/FTS counts, physical database and sidecar bytes,
and scratch cleanup. No network calls or production corpus writes occur.

This complements, not replaces, configured-device I/O probes, graph lane
transactions, real multi-process Mongo coordination and restore drills.
The ordinary CI fixture uses a small disposable workload. Production-scale
execution requires sufficient scratch capacity and the target device, and
must not be inferred from a source-only pass. Actual service access,
industrial workload receipts, power-loss and live production topology
qualification are separate acceptance requirements.
