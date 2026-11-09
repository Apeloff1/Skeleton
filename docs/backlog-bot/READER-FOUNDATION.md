# Backlog Reader Foundation

The canonical backlog-reader foundation lives under `skeleton.automation` and is deliberately static and bounded.

## Trust boundary

Repository file contents are untrusted data. The reader and indexer do not import repository modules, execute code, deserialize YAML/Pickle objects, run shell commands, or resolve arbitrary paths. Inputs are bounded by file size and document count before they are admitted to the index.

## Reader contract

`RepositoryReader` validates repository-relative normalized paths, skips common generated/binary/vendor paths, bounds file size/count, records SHA-256 fingerprints, and extracts Markdown-style headings as inert text.

## Static index contract

`RepositoryIndexBuilder` consumes already-bounded text. Python symbols and imports are extracted with `ast.parse()` only; syntax-invalid Python fails closed for symbol/import extraction. JavaScript/TypeScript indexing uses conservative lexical patterns. Dependency parsing is limited to recognized declaration files and sections.

The resulting index is deterministic and intended as evidence for later backlog reasoning. It is not proof that code is correct, safe, reachable, or executable.
