# Installed application status — 2026-10-28

The repository candidate and the running VM are at different revisions. Four
application services are running and the idle installation doctor passed, but
the current source has not been deployed to those services. Generated-game
playback, dependency-security qualification and consumer release remain open.
The [October 26 report](CONSUMER_READINESS_2026-10-26.md) records earlier
installation, browser and model observations in detail.

## Source and running installation

Two merges reconciled current upstream and studio histories with the installation
work. The resulting branch is `codex/consumer-runtime-readiness-2026-10-25`;
[PR #4357](https://github.com/Apeloff1/Skeleton/pull/4357) is an open draft against
`main`, not a merged release. The integrated runtime source includes commit
`3088c797`; subsequent Windows installer workflow changes are under review.

The VM still runs the October 26 engine and backend images built from `99a75ea8`
and the frontend image built from `704fd359`. Current source fixes, including
the planner changes below, have not been exercised in a newly built installation.
The idle doctor reported platform, configuration and services ready with no next
steps. At the user's request, the inactive Qwen3 rollback model, an old inactive
frontend image and a clean temporary Jeeves checkout were removed. The active
coding model and application data were preserved; approximately 5.5 GiB remained
free after cleanup. A guarded cold image build needs about 6 GiB of free space.
The backend was recreated from the same previously installed image with the current
session proxy after idle, space and identity checks; its data mounts and volumes
were preserved. The engine still has its earlier proxy configuration. Current
source changes remain undeployed. The user requested no further VM rebuild in this
pass; the next intended installation target is the Windows laptop.

Previously observed finite workflows include authenticated chat and reload,
owner-scoped source access, a consent-bound public capture, original-world human
and AI play, two training episodes and source export. Those observations remain
bounded to the earlier installation and are not universal emulation or quality
certification.

After the backend proxy update, a fresh bounded capture from example.com retained
one document and its provenance using two requests and 1,154 bytes. An exact run
replay matched; the source remained unreviewed and an anonymous request was denied.
This is a current-session crawler observation, not a general network or source
quality guarantee.

## Changes and open issues

The studio planner's native-model context admission now accounts for role framing
and the model-visible structured-output schema. Requests that cannot fit the
configured context fail with a typed capacity error rather than starting a call
that cannot be admitted. This covers the planner's admission calculation; later
cooperative stages can add context and still require their own capacity checks.
The source change does not enlarge the model's context or establish that a
particular creative task fits.

The `node-forge` lock was restored to the reviewed 1.4.2 package and its patch
hook was updated. On October 28, public advisory metadata listed the affected
range for [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv)
as `<=1.4.0`, while reporting no `first_patched_version`. The repository's
separate advisory gate still failed with its older snapshot. The package update
is not a security-release signoff.

The optional full-profile Chroma service has a persistence mismatch: the pinned
image writes to `/data`, while Compose mounts its named volume at `/chroma/chroma`.
Data in the container filesystem can be lost on removal or recreation. Preserve
existing Chroma containers and their data until a verified recovery and migration
plan is available. The current source includes a full-profile heartbeat check and
a [persistence warning](../APP_ASSEMBLY.md#application-surfaces); the mismatch is
not yet fixed. The default profile does not require Chroma for bounded lexical
retrieval.

The latest observed AI repair completed one model turn but proposed eight
identical edits that would introduce a `const` reassignment error. The existing
duplicate-edit guard rejected the proposal and preserved the source. A temporary
change that would have normalized identical edits was reverted after examining
the actual proposal. No successful post-fix game or new browser gameplay proof
was established. A completed model operation and an advisory model score do not
certify playable output.

## Windows laptop installation

The intended laptop path is Windows x64 using WSL2 and Docker Desktop. A manual
Windows installer workflow was restored in the candidate. On Linux, 153 combined
first-install and Windows contract cases passed, as did four mocked-Windows
offline browser lifecycle cases. A workflow and archive suite passed 43 cases
and 12 subtests. A separate minimal-dependency probe passed 76 cases and skipped
five requiring PyTorch. These overlapping checks do not replace running on Windows.

The full workflow secret-output scan passed. The CI tier gate failed at its
existing count of 22 automatic triggers against a limit of 20; the restored
Windows installer workflow is manual-only and adds no automatic trigger. Actual
native Windows, WSL2, Docker Desktop and `Setup.exe` execution remain unverified.

## Verification and remaining gates

Seven fast architecture, construction, interface and file-tree validators passed.
Focused merged-source suites passed across installation, provider execution,
repository context, local inference and private media; the planner capacity
suite passed 35 cases and the native inference suite passed 77 cases. These runs
overlap and do not constitute a full repository pass. The full provider-bootstrap
scan subsequently passed on the final runtime source.

The historical broader campaign recorded 52,149 passes, 2,674 failures, 269
errors and 215 skips across 4,442 files. Current-source image rollout, a working
generated-game browser observation, dependency
advisory review and a Chroma persistence migration remain open. The legacy
GameForge governed-export adapter also remains unavailable without its remote
artifact-delivery owner. The VM has no approved native console core, and
Windows/macOS native builds, arbitrary-ROM understanding and universal console
compatibility were not qualified.

Numeric learning and retained lessons do not establish automatic transformer
weight training or guaranteed improvement over commercial games. This status
does not certify consumer, enterprise, security or production readiness.
