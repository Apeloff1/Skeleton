# Original Game Studio: Jeeves, Dragon, Companion and Mirror Room

Status: executable **offline vertical slice**. Not a claim of universal console
SDK access, trained game-creation AI, an automated legal opinion, a commercial
release certification, or complete cross-era game production.

## Production architecture

| Lane | Authority | Actual shipped implementation | Future integration |
| --- | --- | --- | --- |
| Knowledge | Canonical reviewed knowledge and RightsLedger | Research/reference APIs; no unreviewed data in executable game scripts | Source rights/version governance on every external almanac |
| Jeeves | Plan, arbitrate, review, block release | Typed ToolFabric discovery and scoped tool plans; consumer release checklist | Provider model bridge, human review queues, signed policy delegation |
| Dragon | Produce original assets/games within approved tool envelope | Canonical generated or authored tile games, Python reference simulation, browser+Godot source outputs | Additional engines, animation, narrative, orchestration runtime |
| Companion | Learn by building and playtesting original prototypes | Up to eight *real*, separately executable browser and Godot practice-game bundles per session, each replay proven | Personalized learner, skill atlas, curated supervised training |
| Mirror room | Adversarial independent evaluator | 64-512 deterministic executions against state transitions, replay chain, package hashes; failure gate | Native fuzz/UX runs, independent rival models, asset originality review |
| Consumer | Gate evidence and prepare release | Atomic original HTML/Godot source package, nested practice games, provenance hashes, shipping checklist | Signing, accessibility, real hardware, malware/AV, distribution rights |

Only the original-game compiler, deterministic simulator, offline browser
renderer, Godot source renderer, editor, tool planner and mirror tests actually
execute inside this studio. External tools cannot execute just because their
adapter metadata appears in a catalog. Tool requests are scoped by actor, phase,
resource units, declared side effects and pinned implementation digest.

## Run an end-to-end studio session

Write `intent.json` using exactly these validated fields:

```json
{
  "project_id": "my-original-homebrew-2026",
  "title": "Star Garden Labyrinth",
  "subtitle": "An original multi-level browser and Godot game.",
  "seed": 20261011,
  "width": 15,
  "height": 13,
  "levels": 2,
  "collectibles_per_level": 2,
  "hazards_per_level": 3,
  "theme": "space",
  "starting_health": 4
}
```

Then run, with local operator authorization established separately:

```shell
python -m skeleton.ai.game_builder.original_game_studio_cli \
  --intent intent.json \
  --output /tmp/my-original-game \
  --mirror-attempts 128 \
  --companion-practice 2 \
  --trusted-local-operator
```

The output directory must not already exist. No network calls, auto-publishing,
external model API calls or source harvesting are part of this command.

Generated consumer-candidate files:

- `index.html`: runnable offline original browser game.
- `tile-editor.html`: offline original tile authoring and review tool.
- `godot/project.godot`, `godot/scripts/main.gd`, `godot/world.json`:
  editable Godot 4 source game.
- `proof/verified_solution.json` and `godot/proof.json`: reference winning
  sequence and final state, independently checkable by Python and Godot.
- `studio/pipeline.json`: three content-addressed production stages.
- `studio/jeeves_dragon_tools.json`: evaluated tool plan, scope and budget.
- `studio/mirror_room.json`: detailed per-attempt checks and evidence digests.
- `studio/consumer_gate.json`: human/legal/hardware/distribution blockers.
- `studio/companion_practice.json`: capability XP derived from completed
  independently winning games, not from imaginary training.
- `practice/slot-01/`, etc.: **full** separately playable browser+Godot
  game source packages and their own proof, editor and integrity manifest.
- `release.json`: hashes of all top-level and nested deliverables.

To use an original designer-authored level instead, create a complete
`skeleton.game_builder.authored_tiles.v1` document using `tile-editor.html`.
Pass `--authored-world tiles.json --human-reviewed`; author approval does not
mean automatic copyright, trademark or distribution clearance.

## Rights-reviewed inspiration without copyrighted-expression copying

The studio API now accepts the canonical `ReviewedKnowledgeStore`,
`KnowledgeBrief` and `RightsLedger` as one indivisible research handoff:

```python
from skeleton.ai.game_builder import run_original_game_studio

session = run_original_game_studio(
    intent,
    authorized=True,
    reviewed_library=reviewed_library,
    research_brief=reviewed_design_brief,
    rights_ledger=canonical_rights_ledger,
    human_research_approved=True,
    mirror_attempts=128,
    companion_practice_games=2,
)
```

The knowledge store must have fresh reviewed citations in `design_reference`
scope; every referenced source must independently match its RightsLedger
revision, evidence and permitted use. The compiler generates original geometry
and scripts before research clearance; research may inform design decisions but
cannot turn a quotation, source code or game asset into runnable expression.
Reference clearance has no model-training or consumer-publication authority.
Missing approval or a mismatch stops the build before output.

The new `tests.test_game_builder_studio_research` exercises complete
knowledge/rights/game/replay/mirror/consumer handoff and its negative cases.
The local CLI deliberately does not deserialize arbitrary rights or model
objects from untrusted JSON; a trusted application integration must provide
these typed owners.

## Mirror-room threat coverage

Every probe actually invokes the canonical simulator, replay verifier or
package-integrity constructor. Twelve independent adversarial families exercise:

1. Correct replay of a real sample prefix;
2. Rejection of unauthorized actions;
3. Rejection of injected and unsupported actions;
4. Rejection of a wrong-world state;
5. Rejection of inflated player health;
6. Detection of forged replay receipt chains;
7. Detection of a forged expected final score;
8. Detection of mutated proof actions;
9. Rejection of actions after winning;
10. Detection of a modified executable/source file;
11. Detection of a modified release hash;
12. Independent reproduction of a real transition.

Probes use a seed derived from the game's content digest, and produce
deterministic results that can be replayed later. **Passing all probes does not
prove gameplay quality, originality, security or freedom from defects.** New
domains must add executable probes rather than synthetic “review attempts.”
If a probe fails, source export through this studio fails closed.

## Homebrew and legal boundaries

Original source and freely licensed tooling enable lawful homebrew work in
many contexts; permission to publish a specific platform build requires
case-by-case review. The pipeline refuses to treat a copyrighted game asset,
trademarked identity, proprietary console signing key, extracted firmware or
vendor SDK as an automatically usable input. Research/reference ideas are not
equivalent to redistribution licenses, and similarity checks are not legal
opinions. Open-source code carries its own license and attribution duties;
this tool records declared adapter licenses but does not conclude compliance.

Godot Linux and Windows presets produce unsigned builds in GitHub CI. The
existing Ubuntu native lane has already exported two real desktop binaries
and executed its Linux binary. A cross-compiled Windows file alone does
**not** demonstrate Windows runtime or target-hardware compatibility.

The consumer checklist defaults all externally-dependent evidence to false:
rights review, user playtests, native hardware checks, accessibility,
localization, malware checks, code signing, platform permission and explicit
publication approval. Even when Python and native gameplay proofs pass,
the source release remains a **release candidate** until these gates are
completed through separate authenticated evidence and sign-off.

## Tool adapter architecture

`ToolSpec` records:

- tool ID, capability, actors allowed, pipeline phases allowed;
- builtin or external provenance;
- bounded resource cost and declared side effects;
- mandatory license declaration;
- pinned external adapter digest.

`ToolFabric.discover(actor, phase)` only lists capabilities; it never calls
them. `ToolFabric.plan(requests, authorized=True, ...)` enforces role and
phase permissions, resource budgets, write authorization and pinned external
allowlists, and emits a content-addressed plan with **external_blocked**.
Do not interpret granting a plan as executing an untrusted binary; the actual
adapter must be installed, isolated, permissioned and independently audited.

Near-term adapter targets include open-source asset pipelines (Blender, Krita,
GIMP, Inkscape, Tiled, FFmpeg and Audacity), physically available retro console
toolchains and debuggers, original music/sfx generators, more open-source game
engines and emulators, plus modern hardware QA. These are *planned adapters*,
not asserted as connected, licensed or executable by this patch.

## Independent consumer qualification and sign-off

The source package defaults to `release-blocked`. A new independent
`consumer_release_assurance` layer verifies external review receipts before
a caller can classify a candidate as ready for *authorized* publication:

```python
from datetime import datetime, timezone
from skeleton.ai.game_builder.consumer_release_assurance import assess_consumer_release

review = assess_consumer_release(
    session,
    externally_signed_evidence,     # Typed SignedReleaseEvidence entries
    trusted_reviewer_keys,          # TrustedReviewer values held outside artifacts
    now_utc=datetime.now(timezone.utc),
    authorized=True,
)
assert not review.proof.blockers
```

This interface is a trust **verifier**, not a self-signing or self-clearing
publication command. Nine independent authorities are required, one each for
legal/rights, human playtests, native hardware, accessibility, localization,
malware scanning, code signing, platform permission and publisher approval.
Every receipt binds the exact source manifest digest and an independent
evidence-content digest, authenticated with a locally configured HMAC-SHA256
issuer key. Proofs for malware, platform QA, playtest and final publication
carry specific freshness ceilings. Reviewers cannot approve outside their
assigned role; publication is only accepted when all other independent checks
exist and all nine reviewers are distinct.

**Important limitation:** An HMAC establishes custody of a configured key,
not whether the underlying legal conclusion, human test or platform
certification was correct. Trust keys are external secrets, never delivered in
the source bundle, and must come from a separately authenticated organization
or platform verifier. A downstream release system must additionally bind the
exact signed native executable and platform build provenance to the source
manifest; this module does not itself cryptographically verify that mapping,
claim vendor certification or upload to a commercial store.

Windows CI now requests the official Godot release-mode **console wrapper**
(`debug/export_console_wrapper=2`) to observe the native winning-replay
receipt. Unlike mode 1, release mode 2 enables the wrapper when exporting
`--export-release`. No proprietary SDK, rcedit resource editor, or code-sign
credential is used.

## Roadmap to consumer-grade projects

The existing puzzle world is a production **foundation**, not the limit of the
world/story/NPC/engine ambitions. Follow-on real production slices should
implement: narrative and quest state-machine compilation, NPC schedule and
resource-budget simulation, avatar animation and audio, more game genres,
screen reader and control accessibility, localization, editable visual assets,
original procedural asset generation, art/audio legal provenance, advanced
save migration, performance telemetry, native Windows and browser QA,
mobile packaging and unsigned target-specific adapter verification. Every
target platform needs an independently runnable vertical slice before being
labeled `supported`.

Run the new test module:

```shell
python -m unittest tests.test_game_builder_studio_pipeline -v
```

The same test module is included in the Game Builder Native Godot Replay and
AI Game Builder 500 Levels gates. All release artifacts must be compared with
their recorded digests before distribution.
