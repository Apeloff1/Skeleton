# Emerald V7 qualification through a registered main-branch workflow

The earlier V7 draft-only `dragon-atelier-prototype.yml` and new `emerald-v7-*.yml` workflows did **not** yield source jobs in the actual GitHub run inventory. On 17 November 2026, the `main` branch's workflow directory contains the previously registered `.github/workflows/dragon-pilot-source-qualification.yml`, but not `dragon-atelier-prototype.yml`.

This draft adds two **source-head read-only jobs** to the already registered Dragon pilot workflow and extends its event path filters to V7 source and original-asset changes. The original pilot job remains intact. One job tests exact-V7 source files, SHA-bound original-contact-tool staging, real-format evidence receipt reconciliation, hostile archive/GLB fixtures and all source-custody holds. The other job runs only on dedicated V7 `assets/*` branches and verifies **actual Git checkout binary payloads** by all eight SHA-bound original chunks and complete model digest.

All PR jobs use `pull_request` identity, exact PR head checkout, read-only `contents` permission, verified script compilation, and no secrets, model downloads or write tokens. They never run an unreviewed ZIP member as code; archived sources are separately checked against five immutable SHA pins before any external operator executes a contact scan.

A source-only pass must **not** count as remote binary publication, true skinned-mesh full CCD, arbitrary Three.js mixer qualification, physical Unreal/RTX, artistic approval, release provenance or merge readiness. No workflow here authorizes merges or changes the original model-publishing holds.

The *CI activation remains unconfirmed* until an exact-head run of this registered workflow is created and inspected. If GitHub restricts PR workflow updates, no source, binary, or release signoff is inferred from its presence in a branch alone.
