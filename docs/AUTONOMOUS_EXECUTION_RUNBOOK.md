# Autonomous execution runbook

The repository automation path is intentionally fail-closed:

`Automation Traffic Manager → Repository Supervisor → Secretary → registered worker → ordinary pull request`.

## Scheduled operation

The traffic manager runs every ten minutes from the default branch. Admission captures the exact workflow SHA, records the traffic decision identity, rechecks the live default-branch head, and only then queues `supervisor.yml` with that SHA as `expected_base_sha`.

If the default branch advances between admission and dispatch, the run coalesces instead of dispatching stale custody.

## Manual dispatch

Use the **Automation Traffic Manager** workflow when an operator needs a bounded manual admission.

- Keep the workflow ref on the repository default branch.
- `force=true` bypasses soft cooldown/no-demand suppression; hard capacity limits still apply.
- Do not manually invoke a worker module. Workers require Secretary delegation and exact custody tokens.
- The **Repository Supervisor** workflow also supports `workflow_dispatch`; when `expected_base_sha` is supplied it must equal the exact Supervisor execution SHA.

## Required model configuration

The Supervisor planning job reads:

- repository variable `MODEL_API_URL`
- repository variable `MODEL_NAME`
- repository secret `MODEL_API_KEY`

Do not put credentials in plans, issue text, workflow inputs, or generated files. The automation code treats model and repository text as untrusted data.

## Recovery and terminal outcomes

The automation records immutable execution identity and bounded worker evidence in the workflow summary.

Common terminal conditions are:

- **stale custody** — the repository moved after admission; coalesce and let the next admission observe the new SHA.
- **no demand / suppressed** — traffic admission did not authorize another lane; no worker is dispatched.
- **capacity suppression** — runner pressure prevents another lane; wait for the bounded queue/traffic controls to recover.
- **worker failure** — inspect the Secretary failsafe report and worker evidence before retrying.
- **worker timeout** — treat the result as ambiguous; do not blindly replay it because a branch or PR may already exist.
- **validation/publication failure** — keep the resulting evidence and fix the failing validation boundary before retrying.

The Secretary may perform one bounded retry for outcomes explicitly classified as retryable. Retries re-check the exact base SHA and remote base before dispatch.

## Shutdown

For an immediate operational stop:

1. Stop issuing manual traffic-manager dispatches.
2. Do not invoke workers directly.
3. Allow an already-running Supervisor/Secretary execution to reach its bounded timeout or terminal result.
4. Review open worker PRs before any cleanup.
5. Restore normal scheduled operation only after the repository head and automation checks are healthy.

A code-level shutdown or policy change should be made through the normal pull-request and CI path; do not bypass the workflow custody model.

## Verification checklist

Before treating an autonomous run as successful, verify:

1. The traffic admission and Supervisor reference the same 40-character base SHA.
2. Supervisor plan output contains a sealed delegation and execution/snapshot fingerprints.
3. Secretary accepted the delegation and recorded the worker assignment.
4. The worker evidence is bound to the same execution fingerprint.
5. Any repository mutation is on the deterministic worker branch and is represented by an ordinary PR.
6. CI and security gates remain intact.

See `.github/workflows/automation-traffic-manager.yml`, `.github/workflows/supervisor.yml`, and the focused automation tests for the executable contract.
