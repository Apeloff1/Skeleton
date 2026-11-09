# Migration conflict notes

The automation-agent migration PR requires a real three-way merge against current `main`. The connector cannot perform a rebase/cherry-pick, so this branch records the unresolved state rather than replacing current metadata with stale PR content.

Affected migration-control files: `.machine/repository.toml`, `docs/architecture/REPOSITORY_ATLAS.md`, `machine/ai_file_tree.json`, `machine/repository_migration_plan.json`, `scripts/check_ai_file_tree.py`.
