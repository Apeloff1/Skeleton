# Build augmentation note

- **Batch IDs:** B___
- **Area:**
- **Author/agent:** ai:chatgpt
- **Contribution mode:** authored | assisted | review | automation | human
- **Intent:**

Use canonical actor IDs or registered aliases from `repo-intel/contributors.json`. List every human, AI agent, bot, automation, or orchestrator that materially contributed to the work unit. If a new actor is not registered, add it to `repo-intel/contributors.json` rather than inventing attribution. Git authorship/co-authorship, this handoff declaration, and operational/tool presence are separate evidence classes.

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

## Contribution/provenance note

Record any attribution edge case that affects interpretation: connector/shared human identity, squash/rebase/cherry-pick, generated commit, delegated bot chain, multiple AI agents, unknown model version, imported branch/snapshot, or automation acting on behalf of another actor. Do not infer missing authorship from a branch name or tool mention.

## Noticeable gaps / next augmentation

State remaining incomplete behavior, missing tests, unsupported targets, uncertain assumptions, or next high-leverage batch. Do not hide gaps to make the work look complete.

## Build handoff

- [ ] `make repo-intel`
- [ ] relevant focused tests
- [ ] `make repo-intel-check`
- [ ] canonical Author/agent provenance recorded
- [ ] batch claim/release state updated if applicable
