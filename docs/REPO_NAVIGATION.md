# Whole-repository AI navigation and duplication atlas

This is a deterministic, byte-exact Git-tree index. Every tracked file is
included, including archived snapshots, generated sources and binary assets.
It complements the canonical docs/architecture/REPOSITORY_ATLAS.md.

## Minimal-context navigation
1. Read machine/repo_navigation/manifest.json first for counts, provenance and routing.
2. Read features.json for groups, primary zones, languages, tests and entrypoints.
3. Read tree.json for folder hierarchy and file counts.
4. Open only the relevant files/<group>.jsonl shard, never all files.
   Fields: p=path, g=Git OID, b=size, m=mode, t=object type, z=zone, f=feature.
5. Read duplicates.json for identical Git blobs; near_duplicates.json is a
   heuristic candidate queue, not automatic permission to consolidate.
6. For symbols/imports/dependency graph/test links, use existing
   skeleton.repo_machine and its repository-machine workflow artifacts.

Ownership, criticality and lifecycle follow .machine/repository.toml,
first matching zone wins. Governing AI migration map: machine/ai_file_tree.json.

## Auto refresh

python scripts/build_repo_navigation.py --root .

The dedicated GitHub Action runs on main pushes, daily and manually, tests the
builder and refreshes indexes in a reviewable PR, never silently to main.
It also publishes complete workflow artifacts. The generated directory is
excluded from source input to avoid self-index loops.

## Safety

Byte equality does not imply equal purpose. Some mirrors, compatibility shims,
tests, fixtures and archived snapshots are intentionally duplicated.
Near similarity uses a bounded 5-token-shingle Jaccard comparison; check its
skipped/budget counters before claiming coverage of near-duplicate behavior.
No files are automatically moved, removed, renamed or given canonical authority.
Before reorganization check imports, dynamic references, APIs, licensing,
packaging, generated paths, tests, provenance and owner approvals. Preserve the
existing mirror-then-explicit-cutover policy and runtime contracts.
