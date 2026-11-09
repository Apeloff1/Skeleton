# Jeeves studio: native observations, composed learning and app operation

This continuation develops the studio application. It adds stronger authoring,
source-bound native gameplay measurements, composed adversarial proposals,
recoverable Jeeves workflows and observed operator readiness. It does not declare
the AI masterplan complete, promote a model, deploy the application or merge the
draft pull request. No automated tests were authored or run, as requested.

## Authoring and native execution

The existing Game Boy starter compiler now consumes the supported authored scene
graph: hierarchical offsets/visibility, real 8×8 sprite atlas frames, fixed-tick
animation timelines and moving/visible goals. Its generated kernel evaluates the
bounded 32-phase tables on the console. Unsupported variables, rules and physics
remain explicit compatibility findings. The editor exposes native compatibility
against the saved source; unsaved changes make that projection stale.

Trusted authored NES and Game Boy builds expose fixed source-bound RAM layouts.
The build issuer freezes the exact kernel, data binding, observation descriptor,
artifact and current source. Admission recomputes the descriptor from the frozen
issuer files. The compatible approved core then measures actual player and goal
positions, health, ticks, camera and terminal flags. A bounded boot grace precedes
signature enforcement; snapshots bind the captured RAM hash. Training and the
live viewport consume these measurements. Arbitrary commercial ROMs remain
visual observations without inferred score, health or success.

The actual native graph workload compiled a 32 KiB Game Boy cartridge and ran
81 Gambatte steps. Two atlas frames matched expected RGB pixels exactly; RAM
showed changing goal positions and visibility. A separate NES build produced
40,976 bytes and ran 33 FCEUmm steps with the actual RAM signature. These are
emulator measurements of authored cartridges, not physical-console certification.

Design simulation also exposes measured control/contact/collision events and
bounded review geometry. Dragon review checks source-bound blocked spawns,
available routes, quest/resource producers and executed control responses. It
returns typed inspect/edit drafts with exact version, manifest, record and
executed-step evidence. Applying a draft remains an explicit scoped operation;
a subsequent actual play/review must measure its effect.

## Remembered improvement

Campaign v3 composes two to four supported parameter changes rather than relying
only on isolated scalar mutations. It validates candidates, avoids duplicates
and uses bounded measured trial memory plus counterexamples to rank proposals.
Learning can select least-visited exploration and real one-to-sixteen-step
discounted reward backups. Publication remains episode-atomic with one numerical
update per transition. The worker instances collect independent actual rollouts;
they never share a mutable learner.

The final retained workload executed eight rounds, 10,752 transitions, 1,536
candidate Q updates and 384 parent updates. It reopened the checkpoint between
rounds four and five, retained eight search receipts, fourteen counterexamples
and thirty-two lessons, and attempted two composed proposals. One continuation
passed because action diversity increased. Return, completion and survival did
not improve; seven subsequent candidates were rejected. This demonstrates
remembered measured selection, not subjective game quality or 100,000-round
endurance. A separate exploration comparison visited eleven states rather than
seven, but achieved a worse mean return; that result is retained without a
performance claim.

Configured campaigns may request 100,000 rounds through bounded durable slices.
The numerical learner still enforces its lifetime episode/update and ancestry
limits. The application does not silently discard lineage or reset those limits
to make an endurance claim. Automatic continuation has finite authorization and
requires the preceding physical worker to quiesce.

## Jeeves app use and recovery

Goal journal v2 seals the original intent and grants, contiguous receipt history,
pending work and resulting state. BSON timestamps are hashed in canonical UTC
milliseconds so an actual Mongo round trip preserves the seal. Earlier unverified
journals are not automatically repaired or granted execution authority.

The planner discovers the exact typed application schemas and current scoped
source. A bounded decision can queue up to four commands, each checkpointed
before dispatch and joined to actual child job/play completion. Fixed receipt
references select issued identities; they do not evaluate arbitrary paths or
code. Edits retain the owning project/version/manifest checks. Compound workflows,
retry, child resume/stop, finite time renewal and paged history are visible in the
studio. Renewal never resets counters or changes the original edit/job grants.

Actual model decisions flow through EngineChat → EngineText → EngineClient → the
existing canonical execution/provider runtime. A validated frozen JSON schema
travels through that boundary to actual local grammar enforcement. Response text
and deterministic operation/execution identities must match authenticated
canonical terminal receipts before an app command executes. Unknown admission,
404, running work and unavailable providers do not authorize a fresh model
attempt. A separately budgeted retry requires actual terminal proof.

The local provider can activate either its existing model artifact or one
digest-pinned standalone llama.cpp deployment manifest. This uses the existing
provider activation, model loader, admission, cancellation and receipt owners;
the studio has no model SDK, direct inference transport or additional provider.
The existing service-authenticated engine provider read route supplies sanitized
availability observations without operator paths or credentials.

## Actual application operation and operator setup

The full existing backend and canonical engine were started against a private
durable Mongo 8.0 instance. A real authenticated studio account used the actual
API and canonical storage admission. The local model is Qwen3-0.6B-Q8_0, pinned
to its downloaded artifact and llama.cpp b11429 executable. This small CPU model
is an integration workload, not a claim of best available planning quality.

An actual governed Game Boy build was admitted, compiled, registered and trained
through the authenticated application. Two episodes committed 128 Q updates;
512 held-out steps measured a candidate return of 1.2487 against 1.3683 for the
seeded random baseline. The policy was reopened from canonical storage and used
by a real AI-controlled Gambatte session for 64 steps and 65 frames. Exact RAM
showed movement from (16,16) to (26,12), health five and no goal completion.
The session drained with zero physical workers/credits remaining. This establishes
working app transport and native learning, with no measured quality gain.

The canonical CPU model also completed an actual structured generation with one
provider receipt and normalized usage estimates of 5,989 input/78 output tokens. Its contradictory completion
flag and requested operation were rejected by the host. The schema now encodes
those two states as exclusive alternatives; the failed run remains in evidence.
Successful model planning must be recorded separately from successful generation.

A subsequent strict-schema goal completed through the actual authenticated API.
The first canonical decision executed `console.inspect` against the current
project; the second declared completion with no operation. Both model turns have
canonical provider receipts and the goal journal is verified. The system records
`planner_declared_done`, while `goal_satisfaction_verified` remains false: this
is a successful model/app workflow, not an independent quality assessment.

The Studio overview reports current storage/admission, canonical provider,
approved cores, compiler prerequisites, recovery scheduler and effective worker
capacity. Missing observations remain explicit. On this host, the effective
cgroup limit permits one training actor and one live play, combined capacity two;
the global ceiling of eight is not presented as eight currently available actors.
Project work links point to actual issued jobs, plays, campaigns and goals.

Operators configure existing backend Mongo settings, the shared engine service
identity, one approved model/provider, the approved core registry and compiler
SDK roots. `SKL_GAME_CONSOLE_SDK_ROOTS` is a JSON array of trusted absolute roots.
No user input selects executable paths, core libraries or shell commands.
Readiness indicates observed prerequisites; each actual execution still has its
own source, rights, issuer, capacity and deadline checks.

The real app exposed and fixed a shutdown loop in the existing signal handler.
After its bounded drain, it now restores/delegates the original Uvicorn handlers
and completes background task cleanup. Actual shutdown logs record a clean exit.

Final API/model/native operation results and exact hashes are recorded in
`machine/ai_game_studio_session_evidence_2026-10-14.json` under the separate
runtime continuation entry. Earlier session receipts remain historical.

## Build, validation and limits

The final production web export contains 186 HTML routes, 67 JavaScript files and
292 files totaling 33,419,371 bytes. The deterministic archive is
`/workspace/scratch/jeeves-studio-app-observed-final.zip`, 9,218,374 bytes, SHA256
`bb81125305eac477595a1d14f14c7742ad0c43cbf3e10183d902aca438f34e37`.
It requires the configured backend; it has not been deployed.

Source validation covers mandatory architecture/construction/interface/provider
and enterprise validators, canonical mirror parity, Python compilation/lint,
typed frontend compilation/lint and the production export. These are distinct
from automated tests and from measured gameplay/model workloads.

The inventory remains 169 target profiles, 34 compiled native cores and 29
operator-approved core configurations mapping 46 hardware targets. Enumeration,
installed cores, compilation, working title execution and full game creation are
different capabilities. Every-console compatibility, full native graph semantics,
all-title ROM comprehension, subjective studio quality, original-game superiority,
cross-OS execution and 100,000 executed retries remain unverified.
