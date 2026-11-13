# Operate measured game-builder refinement

The original-game assistant can run a bounded cycle of baseline execution,
source editing, simulation, numerical review and refinement before packaging.
The application checks actual owner receipts at the current source head. A
model's explanation cannot satisfy the acceptance gate.

This is measured acceptance under a selected workload. It does not certify
subjective game quality, console compatibility, statistical superiority or
generalization to games the system has not executed. The retained observations
and constraints do not update language-model weights.

Start with [installation and AI readiness](FIRST_INSTALL_AI_AND_CRAWLER.md) and
[the crawler, builder and training workflow](STUDIO_CRAWLER_BUILDER_TRAINING.md).
Use an authenticated editor/admin account and an ordinary base project or an
existing saved original successor. Console-editor and studio-session projects
require a separate original project.

## Grant a finite workflow

In the game-learning assistant, select the original workflow, authorize edits,
select simulation and review, then enable measured quality. Package and export
remain optional requested outcomes. The measured-quality preset grants sixteen
actions, sixteen model calls and six jobs. These are upper bounds, rather than
an instruction to consume every credit.

The equivalent authenticated request is
`POST /api/game-studio-agent/projects/{project_id}/goals`:

```json
{
  "expected_version": 1,
  "idempotency_key": "original-quality-pass-001",
  "goal": "Improve the saved original world using observed control and visibility findings, preserve the reference on rejection, then package and prepare both exports.",
  "execution_mode": "run",
  "completion_mode": "original",
  "allow_edits": true,
  "authorization_seconds": 3600,
  "max_steps": 16,
  "max_model_calls": 16,
  "max_output_tokens": 1024,
  "max_jobs": 6,
  "completion_requirements": ["edit", "simulate", "review", "package", "export"],
  "quality_gate": {
    "schema_version": "skeleton.game.studio_quality_policy.v1",
    "max_refinement_rounds": 2,
    "min_available_frames": 2,
    "min_executed_steps": 1,
    "max_error_findings": 0,
    "max_warning_findings": 128,
    "require_no_regression": true,
    "restore_on_regression": true
  }
}
```

Use the actual current `expected_version` and a fresh request key. Reusing the
same key and identical request replays the original goal; changing its intent
under that key is rejected. The quality policy and resource ceilings remain
sealed to that original intent.

Admission requires `completion_mode: original`, `execution_mode: run`, and both
the `simulate` and `review` requirements. Restoration needs the explicit edit
grant. Omitting `quality_gate` preserves the existing workflow behavior.

The limits are:

| Grant or threshold | Bound |
| --- | --- |
| Actions | 1–16 |
| Model calls | 1–16; default 4 |
| Jobs | 0–8; default 2 |
| Authorization window | 60–3,600 seconds |
| Decision output | 256–4,096 tokens; default 1,024 |
| Refinement rounds | 1–4; default 2 |
| Minimum available frames | 1–25; default 2 |
| Minimum executed review steps | 1–512; default 1 |
| Maximum observed error/warning findings | 0–128 each |

An initial reference review, candidate reviews, synthesis and packaging consume
ordinary job credits. Simulation consumes an action. A refinement round is a
candidate `world.edit`; an exact incumbent restoration is recorded separately.
Four permitted rounds cannot override a smaller action, job, model or time
grant. The owner refuses another edit when insufficient budget remains for
simulation, review and a requested restoration. It does not silently increase a
budget or renew an expired grant.

The warning threshold defaults to 128 because warnings are measured findings
that often need inspection, including intentional scene behavior. Set a lower
threshold when those observations are unacceptable for the selected workload.
The error threshold defaults to zero. Neither threshold turns the deterministic
observer into a subjective art critic.

## Establish the reference

By default, the first completed positive original-runtime review issued by this
goal becomes its reference. It executes before the first candidate edit. A new
original is synthesized and adopted before that baseline is recorded.

To use an existing reference, supply `quality_gate.baseline_review_job_id`.
That review must belong to the same project and owner, be completed at the
current source head, contain actual frames and steps, and carry the current
original-runtime comparison contract. A chained review or legacy record lacking
that contract is refused. Run a fresh original reference review in that case.

The reference retains its job ID, input digest, source-head digest, project
version, review digest and protocol digest. Later candidate edits do not replace
that reference. Historical reads recheck live source rights, teacher consent,
policy identity and external-origin revision/epoch restrictions. They authorize
inspection of the recorded observation, rather than execution against an old
world.

## Execute and compare a candidate

For a candidate, the host freezes the reference's seed, episode length, capture
interval and controller protocol. A model cannot choose a more favorable seed
or shorter review after seeing the reference. Source-revision comparison is
limited to the original successor runtime with the same runtime/reviewer
implementation, action/observation/reward contract and admitted workload.
Frozen Q-policy comparisons keep their separate same-source behavior.

Each source edit invalidates previous simulation, review, package and export
facts. The candidate needs positive committed current-source simulation with an
actual frame, then its own completed digest-checked review. Acceptance checks:

1. the configured minimum executed steps and available frames;
2. the configured bounds on observed error and warning findings;
3. a matched original-runtime comparison protocol;
4. no observed regression when `require_no_regression` is enabled.

The paired measurements include task return and available semantic goal/death
observations. Frame-count and offline timing changes are advisory rather than
invented measures of general game quality. A content edit that makes an authored
objective easier can improve its bounded return without making a better game.

The public `goal.quality` projection reports the reference and candidate
identities, observed finding counts, failures, regression metrics, refinement
credits and a receipt digest. Its statuses are `baseline_required`,
`candidate_required`, `accepted`, `rejected`, or `unavailable`. The last status
means current evidence or authority could not be verified; cached acceptance
does not satisfy the gate.

## Reject, restore and refine

A rejected candidate cannot be packaged or exported through the goal. With
`restore_on_regression: true`, the next allowed edit restores the six editable
world sections from the exact issued reference. The host reconstructs those
sections from saved reference bytes and checks the complete source-content
tree. Project versions and per-file revision counters continue increasing;
restoring bytes does not rewind those identities. The model selects the operation but cannot substitute a different
"restored" world. The existing versioned world editor performs the write.

For an explicit operator restoration, read
`GET /api/game-successor/projects/{project_id}/world`, then send
`PATCH /api/game-successor/projects/{project_id}/world` with its current
`expected_version`, `expected_spec_digest`, a fresh `idempotency_key` and the
actual `restore_review_job_id`. Select that reference instead of `changes` or
`edits`. The completed review must belong to this project, retain live source
authority and have the same immutable identity/origins. Restoring the reference
can remove an optional fidelity section introduced by the candidate; it cannot
silently switch to another game's lineage.

Restoration consumes ordinary action/model credits and records the
`restore_incumbent` quality role. It does not reset spent refinement credits or
erase rejected evidence. Another candidate requires another explicitly bounded
edit followed by fresh simulation and review. When refinement capacity is
exhausted, the goal stops with the original reference retained.

With restoration disabled, a rejected candidate can remain in the working
project for inspection or another authorized refinement. Passing numerical
acceptance is still required before packaging/export. Pausing, cancelling,
expiry or an unavailable dependency stops further work; it does not perform an
unrequested restoration after the stop. Inspect the current working head and
the recorded reference before deciding how to continue.

All measured-quality decisions replan after the preceding actual operation.
Compound follow-up queues are disabled for this mode so a queued proposal
cannot bypass a new review result. Ordinary goals retain their existing bounded
compound-action behavior.

## Continue, recover and retain observations

Each advance uses the returned goal version and a new idempotency key. An exact
retry of an uncertain request uses its original request and key. One request
can process one to four serial planner decisions using
`max_planner_decisions` (default one). `wait_for_work_seconds` permits up to ten
seconds of bounded child waiting (default zero). The entire request shares a
20-second dispatch slice and the original goal deadline and resource grants.
Every decision refreshes context from actual committed receipts. Unfinished
work retains its canonical engine operation/execution identity; increasing the
slice does not renew authorization or replenish any budget. An uncertain retry
must preserve both options and the original key. Inspection starts no model work.

The optional browser continuation control sends serial version-fenced advances
only while the route is visible and the current finite goal permits them. It
waits for an actual child job, joins a finished child through the next advance,
and stops for errors, pause/cancellation, expiry or a terminal goal. It does not
renew authorization, replace a failed model attempt or retry a blocked action
without an explicit operator decision.

Use these authenticated owner routes when operating through the API:

| Operation | Route |
| --- | --- |
| Inspect current receipts and continuation hint | `GET /api/game-studio-agent/goals/{goal_id}` |
| Advance within the issued grants | `POST /api/game-studio-agent/goals/{goal_id}/advance` |
| Read sealed action history | `GET /api/game-studio-agent/goals/{goal_id}/history` |
| Pause, resume or cancel | `POST /api/game-studio-agent/goals/{goal_id}/control` |
| Explicitly recover an issued planner/action/child | `POST /api/game-studio-agent/goals/{goal_id}/retry` |
| Explicitly renew time, without replenishing spent budgets | `POST /api/game-studio-agent/goals/{goal_id}/authorization` |
| Explicitly adopt the observed current editor revision | `POST /api/game-studio-agent/goals/{goal_id}/source-refresh` |

Live execution remains under the existing goal lease and canonical EngineChat.
Cancellation takes effect at the current issued-operation boundary. Prepared
editor recovery reuses the exact original editor operation and source rights;
another editor's pending write is not bypassed.

After an external or manual source edit, inspect the current project version and
tree digest before selecting **Refresh source**. That operation requires explicit
acknowledgement, the observed goal version and a new idempotency key. It can adopt
the current revision only after pending planner/action work is resolved; already
issued children must be terminal before they can be joined. The original
baseline, history, consents and spent grants remain intact. Advice and sharing
that are incompatible with the new source structure are withheld. Old uncertain
advance keys retain their original meaning and cannot restart planning against
the refreshed source.

The planner receives bounded round feedback from matched baseline/candidate
reviews and exact edit receipts, including rejected candidates and restorations.
The panel exposes those actual facts. Failed numeric proposals are filtered from
compatible suggestions so the next decision can use the observed rejection;
neither the feedback nor repeated attempts invent an improvement score.

Completed numerical reviews also supply bounded same-project observations to
later original-goal context. Each retains its source, review, input and finding
identities. Only an exact current source/reviewer match is labelled applicable
to the current tree; older observations remain historical constraints requiring
fresh execution. A cited review is revalidated before use. Campaign lessons,
consented demonstrations and approved Dragon references retain their existing
separate authority and training rules.

For packaging, current numerical acceptance supplements the requested owner
facts. It does not certify that a desktop package executed on its target OS,
that an exported file was downloaded, or that arbitrary console content runs.
