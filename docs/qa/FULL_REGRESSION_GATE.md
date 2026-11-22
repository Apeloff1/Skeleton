# Full regression gate

Workflow: `.github/workflows/full-regression-gate.yml`  
Branch that introduced it: `qa/full-regression-gate-20261114`

This is an additive QA gate. It does not edit Grenn's CI lane (`merge-readiness.yml`, `ci.yml`, `backend-quality.yml`, `queue-drain.yml`).

## Why it exists

On draft PRs #5353, #5354 and #5355, the named required checks **Unit**, **Lint Type Security**, **CI/CD** and **Merge Readiness** all completed as `skipped`. The workflow started, but every relevant job used this draft guard in `.github/workflows/merge-readiness.yml`:

```
github.event_name != 'pull_request' || (!github.event.pull_request.draft && github.event.action != 'converted_to_draft' && github.event.action != 'closed')
```

Exact lines on main `c7e29744eb01e426c2cba8f1777a0ec785299ba3`:

- Unit — `unit` job, line 110
- Lint Type Security — `quality_security` job, line 197
- CI/CD — `ci` job (reusable workflow call), line 505
- Merge Readiness — `readiness` job, line 548

GitHub treats a skipped required check as a pass unless the repository is configured otherwise, so a draft PR can look mergeable without running the suite.

Even after those jobs run (for example after `ready_for_review`), newly added repo-root tests still may not execute:

- `tests/run_unit.py` only loads a fixed `TEST_MODULE_NAMES` allowlist (legacy GameForge and physics modules). It does not discover `tests/*.py` in general.
- Canonical Domain Suite shards only `skeleton/testing/test_*.py` (`scripts/run_domain_suite_shard.py`).
- CI/CD **Backend Test** runs `pytest tests/` with `working-directory: ./backend` (`.github/workflows/ci.yml`), so it covers `backend/tests/`, not repo-root `tests/`. A tests-only or skeleton+tests change also sets `backend=false` in `scripts/ci_change_scope.sh`, so that job can skip.

This gate exists so every PR to main, including drafts, runs pytest, frontend lint, and frontend node tests on the exact PR head SHA, and so a skipped job cannot satisfy the aggregate.

## What it runs

The workflow triggers on `pull_request` (`opened`, `synchronize`, `reopened`, `ready_for_review`) with **no draft `if:`**, on `push` to `main`, and on `workflow_dispatch`. Permissions are `contents: read` only. Concurrency is per PR number (or SHA on `main`), cancelling superseded PR runs only.

All jobs check out `${{ github.event.pull_request.head.sha || github.sha }}` and assert `git rev-parse HEAD` equals that value.

| Job | What it does |
|---|---|
| `head-sha` | Pin check only. |
| `python-regression` | Python **3.11.16** (the pin in `merge-readiness.yml` / `ci.yml`; `pyproject.toml` and `backend/pyproject.toml` target 3.11. The production image in `backend/Dockerfile` is `python:3.14-alpine`, which is not the CI/tooling pin). Installs `requirements-dev.txt` and `backend/requirements.txt`, then pins `ruff==0.17.2` and `pytest>=8,<9` as existing gates do. Runs `python -m ruff check skeleton tests backend`. Runs `pytest tests skeleton/testing backend/tests` excluding the `live_service` marker registered in `backend/pyproject.toml`. Writes `--junitxml` and uploads it with the `actions/upload-artifact` pin already used on main. |
| `node-regression` | Node **24.20.0** (the pin in `merge-readiness.yml` / `ci.yml`; there is no `.nvmrc`; `frontend/package.json` `engines.node` is `>=24`). Uses Yarn 1 because `frontend/package.json` declares `packageManager: yarn@1.22.22` and `frontend/yarn.lock` is the lockfile. Installs with `--frozen-lockfile --ignore-scripts`, applies `frontend/scripts/patch-node-modules.js`, runs `yarn lint:ci` and `yarn typecheck`, then every `test:*` script declared in `frontend/package.json`, plus the `node --test` contracts already invoked from Lint Type Security. There is no root-level `node --test` suite (no root `package.json`). |
| `gate` | `needs` all of the above with `if: always()`. Fails unless every needed job result is exactly `success`. **Skipped is not a pass.** |

There is no `continue-on-error` on these steps. Runners are `ubuntu-latest` only.

## How to make it a required check

Making this required is a **branch-protection (or ruleset) change**. Only the repository owner should do that. This PR must not change protection settings.

Suggested owner steps, after the workflow has produced at least one run on `main` or on a PR against `main`:

1. Open the repository's branch protection or ruleset for `main`.
2. Add a required status check named **Full regression gate** (the `gate` job's `name:`). Require it to have completed successfully.
3. Do not treat skipped as success if the ruleset offers that distinction. This workflow already fails the aggregate when a needed job is skipped.
4. Leave Grenn's existing required checks in place. This gate is additional, not a replacement.

Until that owner change is made, the workflow still runs and reports, but it cannot block a merge by itself.
