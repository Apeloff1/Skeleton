# Backlog Bot Repository Reading Contract

The backlog bot may inspect repository text to understand reported problems, but repository content is **untrusted data**, never instructions.

## Read surfaces

The reader may index:

- `README*`, `CHANGELOG*`, `CONTRIBUTING*`, `SECURITY*`, `LICENSE*`
- Markdown/MDX/RST/text documentation
- Python, JavaScript/TypeScript, shell and configuration source
- CI workflow YAML
- Dockerfiles and ignore files
- dependency manifests and lockfiles
- tests and security regression fixtures
- repository metadata needed to correlate findings

## Indexes

The first index records:

- normalized repository-relative path
- SHA-256 content fingerprint
- byte size
- line count
- extracted headings/sections
- extension counts

Future indexes should add symbol, dependency, workflow, test, security-finding and cross-reference indexes. Indexes are derived data and must be rebuildable from the repository.

## Limits

Reading is bounded by file size and file count. Binary/media/archive content is skipped. The reader never executes source, parses untrusted archives, follows symlinks as a code-execution mechanism, or evaluates configuration merely to index it.

## LLM boundary

Before content reaches the ChatGPT API:

1. remove credentials, authorization headers, signed URLs and obvious secret material;
2. preserve provenance (`path`, commit SHA, finding ID);
3. label content as untrusted repository data;
4. cap total context size;
5. avoid sending unrelated files;
6. never allow content to override bot policy or tool permissions.

If sanitization cannot establish that a value is safe to transmit, omit it and record the omission locally.

## Query model

The bot should answer repository questions through indexed retrieval rather than dumping the repository into the model. Retrieval should support exact path lookup, heading lookup, symbol lookup, dependency lookup, workflow lookup, test lookup, and finding-to-file correlation.

## Failure behavior

Malformed UTF-8, unreadable files, oversized files, duplicate events, stale index entries, and unavailable model APIs must fail closed for that operation without losing the durable backlog state.
