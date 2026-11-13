# Current-main architecture pages (Jenkins, 2026-10-31)

Accurate to `main` at `9a73a0cb`. Every page ends with a **References** list of
`module:symbol` entries; `tests/test_architecture_current_docs_refs.py` imports each one
and fails if a module or symbol is renamed or removed.

| Page | Topic |
|---|---|
| [create-app-composition.md](create-app-composition.md) | `create_app` order: routers, mounts, `install_gate`, cortex guard + fingerprint |
| [one-engine-path.md](one-engine-path.md) | The `build_playable_game` single-executor ruling |
| [projects-contract-v1.md](projects-contract-v1.md) | `skeleton.projects.v1` contract and routes |
| [realtime-as-implemented.md](realtime-as-implemented.md) | ADR #4101 as it exists on main, including drift |
| [persistence-deprecation.md](persistence-deprecation.md) | #4122 docstring-only deprecation |
| [seal-design.md](seal-design.md) | `x-gf-seal` HMAC design and known gaps |

The generated route table lives in `docs/api/API_V1_ROUTES.md` (slice C).
