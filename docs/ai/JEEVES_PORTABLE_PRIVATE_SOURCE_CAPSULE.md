# Portable private source capsules (operator-approved, offline)

## Operational purpose

This is a source-delivery feature on top of the existing native GGUF,
canonical SQLite, saved model-source escrow, reviewed patch, selected source
capsule and independent cold verifier. It provides a **portable, bounded,
complete private source archive** that can be carried between machines.
The original source, generated source and private paths never enter normal
CLI stdout. The model never obtains source-write, shell, Git or network
authority.

It does NOT export or install GGUF model weights, provide a sandbox,
install dependencies, prove external Python imports, execute generated code,
assume signed archive identity, authorize program execution, or certify a
complete app. Archive SHA-256 alone is integrity, **not authenticity**:
obtain the expected hash through a separately trusted channel. The owner
must still independently validate external dependencies, device capability,
rights, build, tests and release.

## Source flow

1. A real installed/rights-checked GGUF and SQLite owner generate a strictly
   finite original source proposal, with approved source-context SHA.
2. The original proposal is stored in a private no-clobber escrow. The
   separate review command checks original source identity and generates a
   portable patch. The capsule command includes explicitly selected
   unmodified project sources and binds a SHA to the real reviewed imports.
3. A separate operator approval publishes a new private 0700 capsule with
   0600 exact original/new/edit files and a complete last-written seal.
4. The original capsule is independently cold-verified by full exact
   capsule and seal SHAs. The **export** command reads those exact
   source bytes, recomputes their selected Python AST closure and writes
   one new O_EXCL 0600 archive in an existing 0700 private parent.
5. On another POSIX/WSL2 machine, **inspect** cold-verifies the private
   archive against THREE independent expected digests, including every file
   digest, original/changed kind, seal, tree source identity and closure.
6. Only after a separate **import** approval does the importer make a
   new 0700 directory, recreate source using pinned no-follow descriptors,
   place the seal **LAST**, fsync, and invoke the independent existing cold
   capsule verifier. No original project file is touched.

The archive format is canonical strict JSON with base64 bytes. It is NOT
a tar extractor: traversal paths, symlinks, hardlinks, duplicate JSON keys,
noncanonical representations, unapproved files, hidden sensitive entries,
nonfinite JSON, oversized input and unexpected import closures fail closed.
No extraction is performed until the complete archive has been bounded,
SHA-approved and parsed.

A crash may leave an incomplete private destination. The importer
NEVER silently resumes, overwrites, retries unconfirmed effects, or deletes
a directory that could have been substituted. Inspect and remove incomplete
work manually, then start a NEW destination.

## Command

Use:

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_capsule_transport_cli < request.json
python scripts/jeeves_capsule_transport.py --approve-export < export.json
python scripts/jeeves_capsule_transport.py --approve-import < import.json
```

Each request contains EXACTLY these fields (even null fields must be
present):

```json
{
  "schema": "jeeves.workspace.private-capsule-offline-transport-cli.v1",
  "action": "inspect",
  "original_project_root": "/absolute/trusted/original-project",
  "capsule_directory": null,
  "archive_file": "/absolute/private/archive.jcaps",
  "destination": null,
  "expected_capsule_sha256": "64-lowercase-hex-digest",
  "expected_seal_sha256": "64-lowercase-hex-digest",
  "expected_archive_sha256": "64-lowercase-hex-digest"
}
```

Replace the illustrative digest values with real 64-character lowercase
hexadecimal hashes from the prior independent approvals. Do not put model
responses, private source text, secrets or source path selections in argv.

For **export**: set `action` to `export`, supply
`capsule_directory` as the already cold-verified stage,
`archive_file` as a *new* file in a private directory, and
`expected_archive_sha256` to `null`. Leave `destination` null.
Pass `--approve-export`. The exported receipt contains the NEW full
archive digest. For **import**: set `action` to `import`, leave
`capsule_directory` null, set `destination` to a NEW private directory,
and provide the exact independent archive digest. Pass `--approve-import`.
For inspect, neither consent flag is permitted.

Normal terminal responses contain counts, SHA-256 and explicit non-execution
evidence only; no archive bytes, generated source or private filenames.
The terminal emits one generic hold error to stderr on failure. Do not treat
partial/wrong/failed operations as success.

## Finite boundaries

- At most **72 source files** plus one completion seal.
- At most **1,572,864 bytes of selected and changed source**, and a
  **16,384-byte** complete original seal.
- At most **2,500,000 bytes** in one canonical base64 JSON archive.
- Every source frame is at most 65,536 bytes, bound to exact SHA-256.
- Source paths must be relative, canonical and pass the existing sensitive
  source path restrictions. Import destination is always a NEW directory
  outside the original project. Export refuses paths inside the capsule.
- Requires POSIX/WSL2 descriptor no-follow support. There is deliberately
  no unverified native Windows filesystem backend.

## Qualification

After the source branch is complete, execute on its exact head:

```bash
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_capsule_transport.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_private_capsule*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/laptop_runtime
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Successful source-only tests prove static source handoff contracts, not
physical laptop/CPU/GPU inference, privacy against a compromised host,
real installed-model licensing, signed provenance, unrestricted package
installation, full project readiness or release qualification. Preserve
all draft and mandatory exact-head CI/security holds until satisfied.
