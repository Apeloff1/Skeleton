# Build augmentation note

- **Batch IDs:** B___
- **Area:**
- **Author/agent:**
- **Intent:**

## What changed

Describe the concrete repository/build/product change. Prefer paths, contracts, data flow and externally visible behavior over general claims.

## Validation evidence

List exact commands/tests/evals run and their result. If something was not run, say why.

## Security impact

Record trust-boundary, dependency, secret, network, generated-code, sandbox, provenance or permissions effects. Use `none observed` only after checking the affected surface.

## Quality/performance impact

Record regression coverage, deterministic behavior, build/runtime cost, cache effects, compatibility and any benchmark movement.

## Dependabot/dependency note

Record dependency additions/removals/upgrades and whether an open Dependabot/security item is addressed or newly exposed. If the change does not touch dependencies, say so.

## Noticeable gaps / next augmentation

State remaining incomplete behavior, missing tests, unsupported targets, uncertain assumptions, or next high-leverage batch. Do not hide gaps to make the work look complete.

## Build handoff

- [ ] `make repo-intel`
- [ ] relevant focused tests
- [ ] `make repo-intel-check`
- [ ] batch claim/release state updated if applicable
