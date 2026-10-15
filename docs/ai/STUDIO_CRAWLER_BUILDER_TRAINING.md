# Operate the crawler, builder and learning studio

This continuation connects bounded capture, source review, measured Dragon
practice, compiler/artifact workflows and resumable local policy learning under
the existing application, canonical engine and stores. Catalogue entries and
configured budgets remain separate from completed execution evidence.

Start with [the first-install guide](FIRST_INSTALL_AI_AND_CRAWLER.md). Use an
explicitly configured owner account for editor/admin operations. Keep `.env`,
password files and bearer-token files private.

## Installation and readiness

```bash
python scripts/install_app.py --start
python -m skeleton app doctor --live --studio --json
```

The ordinary installer enables empty Dragon schema initialization and selects
the two existing SQLite files in `backend_data`. Startup creates private empty
schemas, with zero knowledge, approvals, lessons or XP. Existing stores keep
their identities. A disappeared live store returns an explicit error.

The studio doctor can query authenticated backend readiness when given
`--auth-token-file /absolute/private/token.txt`. Its local inventory describes
the CLI host; its server report describes the backend. Inspection never launches
a game, compiler, crawler, model or training job.

Native compilation and emulator execution need approved toolchain/core/firmware
identities and the mandatory sandbox. The default Alpine backend cannot execute
arbitrary glibc host binaries. Use an appropriately configured Linux backend for
native work and inspect its actual readiness. Mounting a directory alone does
not establish ABI or sandbox compatibility.

Acquire only explicitly selected tools through the canonical installer:

```bash
python scripts/install_game_desktop_toolchains.py \
  --root /absolute/private/studio-toolchains --tool rgbds --download
python scripts/install_game_desktop_toolchains.py \
  --root /absolute/private/studio-toolchains --tool rgbds --inspect
```

Without `--download`, provisioning uses only pinned cached inputs. RGBDS/cc65
selection does not silently acquire Go or SDL. Source pins, installed hashes
and receipts are checked before atomic publication. Preserve licences and use
the existing emulator installer for approved cores. Game content and firmware
retain their separate admission workflow.

## Capture, inspect and review

In `/crawler`, create a capture with explicit URLs, purpose, rights references,
consent expiry and request/byte/page budgets. Run grants a finite number of
autonomous slices and a deadline. The existing scheduler consumes that intent;
closing a browser never renews it or restores consumed credits.

Pause disables continuation. Resume restores queue eligibility; a subsequent
Run explicitly grants another bounded window. Cancel stops capture/source use.
Erase removes the source snapshot and its downstream eligibility. The exact
owner can still stop/erase after role demotion or consent expiry. New capture
requires current canonical editor/admin permission.

The source library supports incremental source pages, lexical search and
digest-bound text chunks. Offsets are Unicode codepoints. Preserve whole-content
and passage identities when selecting a quotation. Page instructions remain
untrusted external material. Worker status distinguishes an observed local
executor join from an expired remote lease.

Select an exact quotation, annotate a design observation and select its mechanic.
An editor/admin explicitly approves it as a design reference or rejects it,
with rationale and a separate rights attestation. Approval records an immutable
review and canonical note/revision. Confidence stays uncalibrated; the annotation
has research/design-reference rights, with no model-training permission.

Jeeves retrieves admitted annotations through `knowledge.search`. References
retain capture/consent, revision/note and content identities. Decisions cite
host-issued evidence; stale, unknown or withdrawn identities are rejected before
execution and final completion. Legacy consumers without a trusted source
verifier cannot retrieve reserved crawler-reviewed notes.

## Observe Dragon practice

Explicitly run a practice exercise for a supported reference mechanic. Dragon
plays the fixed coded eight-bit reference environment and retains actual
transitions, rewards, source pins and a measured observation. Limits are 512
steps/ten seconds per attempt, sixteen attempts per owner/day, three attempts
per exact request, one live exercise per owner and two globally. Interrupted
attempts retain actual checkpoints; completed replay returns its original receipt.

`knowledge.practice` retrieves a particular completed exercise with the full
stored receipt SHA and current source checks. Compact model context omits raw
traces/images. The observation retains its runtime and trace identities. This
reference exercise awards no XP and makes no claim that the source proposition
was verified or a policy trained. Existing calibrated promotion/ApprovedLesson
gates remain separate.

## Build, preview and export

Save the console project, then preflight its current source and fixed toolchain
plan. Build starts a governed compiler job. A source-generation plan cannot
satisfy a binary requirement.

Preview a successful admitted artifact through its actual registered runtime.
The bounded preview returns producer/input/toolchain/source digests, simulation
receipt, session/snapshot identity and final-frame evidence. It supports
registered NOOP/movement controls without a learned policy. Existing live-play
controls support interactive and AI-controlled play.

Export current source or a verified binary through authenticated downloads.
Tool results identify bytes actually generated or read, without claiming that a
client downloaded them.

Assistant goals can require `edit`, `build`, `preview` and `export`. Completion
checks use current original-owner receipts at the current project head. A model
stop statement cannot satisfy missing requirements. Historical goals without a
checklist retain their existing unverified-stop semantics.

## Train, observe and retain lessons

The learning panel exposes actual local Q-learning controls: rate, discount,
exploration/decay/floor, least-visited exploration, n-step backup, imitation
strength, episodes and observed worker capacity. Consented human recordings are
explicit demonstration inputs. Native work binds exact admitted content/core
identities.

Parallel actors execute isolated rollouts and commit batches atomically.
Cancellation drains physical work before capacity is released. A cooperative
deadline with a committed checkpoint is interrupted/resumable. Resume retains
original request, policy, source and teacher authority, with no uncommitted
transitions counted as learned.

Evaluation uses disjoint held-out seeds and measured candidate/baseline returns.
Acceptance metadata remains distinct from production promotion. Inspect/export
policy snapshots, evaluation, committed episode evidence and campaign role/lesson
reports. Campaigns retain accepted and rejected experiment lessons for later
bounded proposals. A configured 100,000-round run is a budget; only committed
rounds count as executed.

## Compare review observations

Run an original reference review, then select it as the baseline for another
review at the same source head. Paired comparison requires matching environment,
implementation, seed, planned steps, capture interval and controller protocol.
Different frozen policies can be compared under that protocol. Mismatched or
legacy evidence produces an explicit inconclusive comparison.

Reports retain actual Jeeves execution, Dragon numeric/source findings and
adversarial comparability/regression scrutiny. Priorities link actual findings
to evidence and typed remedial proposals. These deterministic roles are labelled
explicitly; task returns and control observations are not subjective game quality.

Authenticated review export returns the exact completed JSON and an
`X-Content-SHA256` header after current source/policy/baseline checks. Offline
operation timing remains separate from display FPS.

Actual session results are recorded in
`machine/ai_studio_enablement_session_evidence_2026-10-15.json`. Every-console
compatibility, semantic understanding of arbitrary ROMs, universal native editors
and guaranteed improvement remain outside this continuation's evidence.
