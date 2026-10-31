# Consumer installation readiness — 2026-10-31

**Not ready for a tester release.** The target Windows x64 laptop, its WSL2 and
Docker Desktop integration, and a fresh installation of this source have not
been qualified. The prior readiness branch was merged as PR #4357, but merging
it did not establish readiness for a consumer installation.

The hosted [Windows installer run](https://github.com/Apeloff1/Skeleton/actions/runs/40650628582)
passed on October 28 at commit `3a0a9c71023608e503ff557de7cae12b8d1c8d0f`.
It built and exercised Setup on a Windows runner, but it does not validate later
changes or the tester's laptop. Run the Windows installer workflow on the final
source and verify the actual WSL2/Docker installation before release.

## Current blockers

- The default local provider enforces its guard, but Compose does not supply the
  trusted bootstrap dependencies. Local model provisioning alone cannot enable
  chat. See [guarded local readiness](../qa/GUARDED_LOCAL_READINESS_2026-10-28.md).
- The optional Chroma full profile remains blocked until persistence recovery and
  migration have been qualified. Preserve existing containers and volumes; follow
  the [recovery guidance](../APP_ASSEMBLY.md#application-surfaces).
- Marketplace listing and checkout, and new premium checkout, are restricted
  until payment and entitlement delivery are qualified. Existing entitlement
  reads and settlement paths remain available, but some historical orders need
  manual reconciliation if their source, amount, currency or plan cannot be
  verified. The legacy webhook requires a scoped account and is not qualified
  for direct Stripe delivery; concurrent settlement is not yet atomic.
  A generated game has not been demonstrated playable end to end on this source.
- The latest inspected [merge-readiness run](https://github.com/Apeloff1/Skeleton/actions/runs/41185615613)
  reported failures across its canonical test shards on a separate pull request.
  That run is diagnostic evidence, not a result for this branch or a complete
  account of current-main failures. Open fixes must still be integrated and run.
- The frontend advisory gate has an outstanding low-severity dependency finding;
  see [dependency status](../qa/DEPENDENCY_STATUS_2026-10-28.md).
- Runtime supervision validation fails because the runtime contract records
  verification as pending while the masterplan and accountability records carry
  an older signed verification. Reconcile the linked records through an auditable
  requalification or revocation; a changed status alone is not evidence.
- Compose gates frontend startup on backend and engine health. When a required
  backend dependency stays unhealthy during initial startup, the setup page may
  not start to display the failure; use the installer output and service logs.
  A changed startup graph requires qualification on the real deployment.

The earlier VM deployment used older application images and does not qualify
the current source. Passing focused checks, a healthy process, or a model file
on disk is not evidence that the complete studio or local AI is ready.
