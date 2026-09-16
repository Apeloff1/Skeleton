# Overnight Studio: 1,000-role autonomous build team

The Overnight Studio is a bounded, model-assisted development system for advancing Skeleton's game-building and agent capabilities while the maintainer is away.

It models **1,000 specialist roles** but deliberately does not launch 1,000 uncontrolled processes. The registry is the Cartesian product of 25 technical domains, 10 disciplines, and 4 execution lanes. Each scheduled shift deterministically rotates through a bounded cohort and gives only a smaller configured subset model-backed execution slots.

## Directive

The studio optimizes for measurable game-building capability, correctness, integration quality, evaluation quality, and maintainability. It may research the checked-out repository, design improvements, propose additive code, add regression tests, and open review PRs. Competitive claims are not accepted as evidence; improvements must survive tests and normal repository review gates.

## Architecture

`python -m skeleton.automation.studio manifest` emits the canonical 1,000-role machine-readable manifest.

`python -m skeleton.automation.studio cohort --run-key <id> --size 32` deterministically selects a rotating cohort. The default active cohort is 32 roles; the hard maximum is 64.

`python -m skeleton.automation.studio_shift` executes a bounded model-assisted shift. For each selected worker it:

1. reads a small bounded set of repository evidence;
2. sends that evidence plus the worker specialty to the existing bounded Responses API adapter;
3. accepts only strict JSON containing complete UTF-8 file proposals;
4. rejects shell commands, tool calls, malformed JSON, unsafe paths, oversized changes, duplicate paths, and attempts to overwrite existing files the worker was not shown;
5. writes accepted text proposals only into the disposable Actions worktree;
6. appends every decision to JSONL audit evidence.

The scheduled `.github/workflows/overnight-studio.yml` then checks the model report against the actual Git diff, seals the patch with SHA-256, executes studio control tests, executes repository Python tests without the OpenAI key or GitHub token in their environment, restores the exact pre-test patch, records the audit evidence, and publishes a new review branch plus pull request.

## Safety boundaries

The studio cannot directly merge to `main` and generated work is always delivered through a PR.

Model output cannot edit GitHub workflows/actions, authentication/security control planes, secrets, `.env`, dependency manifests, or lockfiles. Those surfaces remain human/trusted-automation work.

Model-produced commands are never executed. The only accepted model-to-builder format is `{ "files": [{"path": ..., "content": ...}] }`.

The OpenAI key is available only to the proposal-generation step. It is explicitly blanked for generated-code tests. The GitHub token is introduced only in the final trusted publication step after the sealed patch has passed validation.

Generated tests can have side effects, so the workflow does not trust the post-test worktree. It resets the repository, removes untracked files, verifies the sealed patch hash, and reapplies that exact patch before publication.

No-op or failed-model shifts remain visible in the GitHub Actions run summary but do not create log-only PR noise. Code-producing runs commit their machine-readable `report.json`, append-only `audit.jsonl`, and patch hash under `docs/studio-runs/<run-id>/` alongside the proposed code.

## Activation

Create a GitHub Actions repository secret named `OPENAI_API_KEY` containing the API key for the account that should fund model calls. Do not commit the key to the repository.

Optionally create a repository Actions variable named `OPENAI_MODEL`. If it is absent the workflow requests `gpt-5.6`.

After this feature PR is merged, the studio runs hourly at minute 17 UTC and can also be started manually with `workflow_dispatch`. Manual runs expose two bounded inputs:

- `cohort_size`: 1-64, default 32.
- `model_calls`: 1-8, default 4.

The default therefore maintains a 1,000-role skill registry, rotates 32 virtual workers into consideration per shift, and funds at most four model-backed proposals per hourly run. Raise the model-call limit only after reviewing API spend and generated PR quality.

## Daily reporting

GitHub remains the source of truth for raw work: workflow logs, generated PRs, committed studio-run audit ledgers, tests, and CI conclusions. The noon progress digest and midnight silent-actions audit should summarize these sources rather than inventing a second hidden state.

The reporting requirement is intentionally separate from the build workflow so email credentials are never present in generated-code execution. Connect the requested mail integration to deliver the two consolidated daily messages.

## Operating principle

The studio should surprise by **validated throughput**, not by unbounded autonomy. More roles broaden expertise and review coverage; bounded execution, deterministic policy, exhaustive logging, and ordinary PR gates keep that scale governable.
