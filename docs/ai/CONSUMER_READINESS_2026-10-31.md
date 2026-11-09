# Consumer installation readiness — 2026-10-31

Updated 2026-11-02 for the multi-draft local AI integration.

**Not ready for a tester release.** The target Windows x64 laptop, its WSL2 and
Docker Desktop integration, and a fresh installation of this source have not
been qualified. The prior readiness branch was merged as PR #4357, but merging
it did not establish readiness for a consumer installation.

The hosted [Windows installer run](https://github.com/Apeloff1/Skeleton/actions/runs/41244524162)
passed at commit `53a4a7b9c537ef764fcb4f7bc43853f693b78d05`: 83 tests passed,
5 PyTorch-dependent tests skipped, Setup built and checksummed, silent installation,
launcher/local-HTTP smoke and uninstall passed. It does not qualify later source
changes, WSL2/Docker integration or the tester's laptop. New source still needs
its own exact-head installer run and real deployment qualification.

## Current construction pass

- Chat review supports one to three sequential draft candidates, immutable
  request/history, joint critique and refinement, and one admitted resource
  grant. Default one-draft checkpoint identities remain unchanged. Focused
  canonical-runtime tests cover restart without repeating committed candidates;
  they do not establish live GGUF quality or independent review.
- Admission/provider outages retain recoverable checkpoints. Persisted retries
  use backoff, bounded startup pagination and scoped maintenance selection.
  Terminal admission-completion reconciliation remains a separate open gap.
- Guard callbacks, source reads and delivery checks respect finite timeouts and
  caller deadlines; timed-out native workers retain physical capacity until
  they return. Mongo epoch reads require a replica-set primary and linearizable
  reads. Native process errors no longer return raw prompt-bearing stderr.
- Training intake uses bounded descriptor reads, stronger split contamination
  checks and staged-byte publication receipts. Interrupted publication preserves
  files for explicit reconciliation. The Cortex lookahead tool now checks exact
  verifier output and refuses impossible grammar masks. This is distinct from
  chat's multi-draft workflow and does not demonstrate an inference speedup.
- Setup and doctor explain missing or invalid local guard configuration using
  fixed public status codes. Preparing weights alone cannot resolve those codes.

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
  A single original successor recipe has rendered and responded to keyboard
  input in Chromium, and one authenticated project build reached a headless
  Godot playtest. These bounded examples do not establish general game quality,
  coverage of generated games or full input-driven play in Godot.
- The inspected [merge-readiness run](https://github.com/Apeloff1/Skeleton/actions/runs/41244524629)
  on `53a4a7b9c` passed frontend, backend, integration, Docker build and GameForge
  jobs. Its domain suite stopped on a stale schema inventory after 3,221 passes;
  incoming main supplies those inventory entries and this branch repairs related
  conformance fixtures. The full-history secret scan reported 651 findings across
  46 files, including historical credential assignments and fixtures. Findings
  need reviewed classification and any necessary credential rotation; there is
  no blanket suppression or certification that the historic values are inactive.
- The frontend advisory gate has an outstanding low-severity dependency finding;
  see [dependency status](../qa/DEPENDENCY_STATUS_2026-10-28.md).
- Runtime supervision validation fails because the runtime contract records
  verification as pending while the masterplan and accountability records carry
  an older signed verification. Reconcile the linked records through an auditable
  requalification or revocation; a changed status alone is not evidence.
- The first-run frontend has **no Compose startup dependency** on the backend
  or guarded AI engine. Waiting even for backend `service_started` would
  transitively require a healthy engine (and MongoDB), hiding setup diagnostics
  precisely when guard bootstrap fails. Backend/engine health dependencies
  remain enforced, and API calls still fail closed when unavailable. This
  change does not enable protected inference, bypass authorization, or certify
  any unhealthy dependency. Operators still need installer output and service
  logs if frontend startup itself fails. The modified Compose graph requires
  real clean-host and Windows/WSL2 qualification.

The earlier VM deployment used older application images and does not qualify
the current source. Passing focused checks, a healthy process, or a model file
on disk is not evidence that the complete studio or local AI is ready.
