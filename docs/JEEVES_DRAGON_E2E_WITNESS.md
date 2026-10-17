# Jeeves ↔ Game Builder ↔ Dragon: E2E observation and operating contract

Status: **implemented local metadata witness; entire end-to-end game production remains unqualified**.
Owner: existing `skeleton/developer/game_cli.py` transport and
`skeleton/developer/jeeves_game_production.py` canonical production quality ledger.
Observer: `skeleton/developer/jeeves_dragon_observer.py`.
Focused contract test: `skeleton/testing/test_jeeves_dragon_observer.py`.

## The three truths

1. **Jeeves** requests plans and proposals; it does not gain tool
   authorization from its own output. Real provider calls still use the
   canonical provider runtime, approvals and shared execution plane.
2. **Game builder** emits, verifies, repairs, and plays games through the
   existing GameForge / director / engine systems. A success-looking UI
   result is not proof that a game was played to completion.
3. **Dragon** observes verified production *receipts*, fingerprints of actual
   local CLI results, and explicitly labeled human operator submissions.
   It does not read hidden reasoning, grab the desktop, mine raw chat,
   change model weights, waive consent, or certify a missing quality gate.

The observer is a **derived local projection**, not a competing event/state
owner. Original canonical production events remain immutable and independently
validated. A missing/corrupt parent receipt invalidates dependent Dragon
observations; storing a hash does not verify the facts claimed by its submitter.

## Local operator walkthrough

First create and initialize a real original-game workspace and its
production ledger. This is the existing workflow:

```sh
python -m skeleton dev game init original-world --dir . --vision "An original, completable adventure"
python -m skeleton dev game jeeves production-init --project ./original-world --target eight_bit_tile_1983 --genre Platformer --period 1985-1989
```

**No observation is enabled by default.** Explicitly opt in for **metadata-only**
observation of actual CLI returns, including Jeeves, builder, director and
Dragon commands:

```sh
python -m skeleton dev game jeeves dragon-observe-start --project ./original-world --consent
python -m skeleton dev game jeeves production-status --project ./original-world
python -m skeleton dev game jeeves dragon-observe-status --project ./original-world
```

When consent is installed, the existing Jeeves CLI transport automatically
witnesses subsequent *command returns*. It saves the command classification,
success/failure state and a SHA-256 of the returned object, **not the object
content or inputs**. Success here means an actual CLI return was observed,
not that a proposed tool effect, quality assessment or entire game succeeded.

For a canonical producer execution slice with a synchronized Dragon journal:

```sh
python -m skeleton dev game jeeves dragon-observe-cycle --project ./original-world --gate source_integrity --passes 2
python -m skeleton dev game jeeves dragon-observe-sync --project ./original-world --page-size 256
python -m skeleton dev game jeeves dragon-observe-lessons --project ./original-world --page 0 --page-size 64
python -m skeleton dev game jeeves dragon-observe-trace --project ./original-world --page 0 --page-size 64 --actor builder
python -m skeleton dev game jeeves dragon-observe-coverage --project ./original-world
```

The trace includes only observed actor, phase, event status, evidence digest,
linkage and timestamp; it never reconstructs private model responses.
The coverage report enumerates every required production gate, expected
independent evaluator, attempt count, Dragon-observed count, last result, and
the next concrete verifier integration step. It does not pass any missing gate.

Production-cycle still owns evaluations. Each invocation is bounded to
1–8 scrutiny passes, but the project may resume for further slices indefinitely.
Sync is bounded to 256 canonical receipts per call; repeat until
`pending_source_events == 0`. These are operational slice limits, not
automatic project time or total-attempt caps. If the game builder succeeds
and the observer crashes, the canonical event remains intact; a later
`dragon-observe-sync` reconciles the missing derived event.

To capture **external instrumentation** from an operator or UI adapter:

```sh
python -m skeleton dev game jeeves dragon-observe-action --project ./original-world --actor jeeves --phase story --event propose --outcome in_progress --evidence <64-lowercase-hex-sha256>
```

This submission is **unverified operator telemetry** even if it says "passed".
The digest must come from the actual producer or instrumented caller; it is not
an authorization, signed reviewer attestation, training label, screen capture,
or quality gate.

To permanently revoke this local observation policy and erase its **derived**
journal while retaining the separately governed production evidence:

```sh
python -m skeleton dev game jeeves dragon-observe-revoke --project ./original-world
```

Revocation leaves a minimal tombstone that blocks re-enablement in that
workspace. Observer files are individually checked before deletion; unknown
files stop cleanup rather than allowing unbounded removal. This command does
not revoke consent or delete personal information held independently by
other product subsystems. Their canonical erasure authorities must be used.

## Observation integrity contract

| Rule | Implementation |
| --- | --- |
| Explicit opt-in | Immutable observer policy requires `--consent`; no observer before it |
| Original producer identity | Policy binds SHA-256 of production quality policy |
| Dedicated derived scope | Project-owned `.jeeves/production/dragon_observer/` |
| Durable writes | Individually fsynced, create-only, atomic hardlink publishing |
| Repair | Replay source production history and only append missing linked events |
| Cross-ledger proof | Source sequence, source event digest, gate, outcome, and evidence digest checked |
| Anti-fabrication | Operator telemetry and actual CLI returns cannot masquerade as canonical quality receipts |
| Privacy | No raw prompts, screenshots, video, audio, tool arguments, or model reasoning |
| Failed checks | Retained, never reinterpreted as passed by observer |
| Lesson candidates | Changed evidence across failed → passed canonical gates, requires independent review |
| Checkpoint promotion | Never; observer writes no model weights |
| Full-game completion | Computed only by the existing independently qualified gate owners |
| Operator visibility | Actor, phase, and outcome counts; stale sync backlog; last event digest |
| Removal | Revoke erases only observer projection and prevents silent restart |
| Runtime discipline | No new daemon, provider, scheduler, privileged tool, database or network endpoint |

**No visual recording is implemented by this milestone.** The `frame_sample`
instrumentation token can index a future externally authorized frame-analysis
receipt, but does not take frames or save video by itself. "Watching the AI" at
present means observing the instrumented public actions and returned receipts
of the local command transport, not inspecting private cognition.

## E2E quality lattice and milestone backlog

Legend: **Wired** = implemented in this change; **Existing** = existing
canonical capability used unchanged; **Open** = requires engineering and
verified evidence before any success claim.

| Track | Milestones | Status / acceptance evidence |
| --- | --- | --- |
| Consent | C01 operator opt-in; C02 immutable policy; C03 source binding; C04 revocation/tombstone | Wired: explicit consent and projection erasure |
| Jeeves | J01 tool result witness; J02 proposal fingerprint; J03 decision lineage; J04 tool-grant identity; J05 provider/latency/token traces; J06 intervention/cancel | J01–J02 partial via CLI; J03–J06 open, must reuse canonical operation/tool receipts |
| Builder | B01 production gate import; B02 recovery after crash; B03 engine build receipt; B04 asset provenance; B05 repair/re-evaluate; B06 matrix coverage | B01–B02 wired; B03–B06 existing/specialized validators must be integrated |
| Director | D01 command return witness; D02 canon snapshots; D03 quest-choice traversal; D04 dialogue coverage; D05 endings and missable branches; D06 camera/audio continuity | D01 wired; D02–D06 open pending executable validators |
| Game runtime | G01 source integrity; G02 binary boot; G03 input map/controller; G04 save/load; G05 checkpoint resume; G06 complete route coverage | G01–G02 existing partial; G03–G06 open for each target/era |
| Dragon study | R01 opt-in ledger; R02 indexed action metadata; R03 canonical source link; R04 failure/recovery candidates; R05 adversarial reviewer; R06 evidence-based almanac handoff | R01–R04 wired as candidates; R05–R06 open |
| Visual capture | V01 approved capture source; V02 application window isolation; V03 visual sampling policy; V04 storage quota/rotation; V05 pause/redaction; V06 frame↔tool correlation | Open; no desktop recorder is bundled |
| Learning | L01 candidate separation; L02 dataset rights; L03 independent review; L04 train/holdout split; L05 real checkpoint updates; L06 benchmark and promotion rollback | L01 wired; L02–L06 open, no model learning asserted |
| Long horizon | H01 append-only history; H02 restart-safe sync; H03 bounded calls; H04 cross-ledger backup/restore; H05 snapshot/index scaling; H06 30-day chaos soak | H01–H03 wired at local scope; H04–H06 open |
| Security | S01 restrictive actor/action vocabulary; S02 hash-link checks; S03 changed source detection; S04 tenant boundary; S05 encryption/retention policy; S06 adversarial prompt injection | S01–S03 wired; S04–S06 must be qualified through canonical host governance |
| Release | P01 full playthrough; P02 cross-platform parity; P03 accessibility; P04 performance; P05 originality/rights; P06 human release signoff | Open; observer cannot bypass any production gate |

### Required future integration sequence

1. **Canonical operation receipts:** attach the witness to the existing
   engine-operation stream and host ToolExecutor after commits, capturing
   step IDs, versioned policy/permissions, pause/resume/cancel and unknown
   outcomes. Do not consume private chains of thought.
2. **Visual evidence adapter:** add opt-in, foreground-only, revocable
   application-window capture using the already governed Dragon media
   capture infrastructure; isolate captures by session, tenant and owner;
   bind frame timestamps to the canonical execution IDs. Redact private
   content before storage, and persist only authorized frames.
3. **Narrative + build + play:** require original world/cast/story/canon,
   mechanics, scenes, assets, animation, sound, integration/build receipts,
   full game-route playthroughs and independent checks for each target.
   Missing validators must remain BLOCKED rather than "complete".
4. **Self-improvement without self-certification:** feed reviewed
   observation candidates to existing Dragon almanac and shadow-weight
   owners. Require explicit rights, source diversity, held-out scores,
   adversarial comparison and checkpoint promotion authorization.
5. **Months-long endurance:** introduce verified snapshots and indexed
   replay to avoid O(history) rescans each operator call; qualify
   multi-process contention, disk-full conditions, crash consistency,
   retention and backup/restore under sustained multi-week work.
6. **Coverage-led full E2E:** bind the controller/emulator game path graph,
   save states, endings, cutscenes and negative paths to deterministic
   playthrough receipts. A boot check must never stand in for full gameplay.

## Regression and repository acceptance

Focused tests: `python -m pytest skeleton/testing/test_jeeves_dragon_observer.py -q`
and `python -m pytest skeleton/testing/test_jeeves_game_completion.py -q`.

The repository mandates independent architecture, provider bootstrap,
capability interface and enterprise implementation validators from
`AGENTS.md`. These checks, actual engine playthroughs, sustained-load
observations, model inference with checkpoints and UI/media playback are
**not established by code review alone**. Track them as outstanding until
real runs produce their exact-head receipts.

The observer supplies visibility, not a guarantee of AAA craftsmanship or
an excuse to waive the studio's immutable production requirements.
