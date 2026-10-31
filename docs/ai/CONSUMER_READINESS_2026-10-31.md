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
- Marketplace listing and checkout are restricted until delivery is qualified.
  A generated game has not been demonstrated playable end to end on this source.
- The latest inspected [merge-readiness run](https://github.com/Apeloff1/Skeleton/actions/runs/41185615613)
  reported failures across its canonical test shards on a separate pull request.
  That run is diagnostic evidence, not a result for this branch or a complete
  account of current-main failures. Open fixes must still be integrated and run.
- The frontend advisory gate has an outstanding low-severity dependency finding;
  see [dependency status](../qa/DEPENDENCY_STATUS_2026-10-28.md).

The earlier VM deployment used older application images and does not qualify
the current source. Passing focused checks, a healthy process, or a model file
on disk is not evidence that the complete studio or local AI is ready.
