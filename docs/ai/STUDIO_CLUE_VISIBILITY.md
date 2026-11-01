# Studio A — source-bound clue visibility

Owner: canonical `skeleton/ai/game_builder` game-production compiler; static
Jeeves adapter in `skeleton/ai/agents/jeeves` with governed mirror.

A user supplies the explicit prompt `build a source-bound clue trail` or an
edited typed `{"clues":[{"id", "scene_id", "visible_after_stage",
"spoils_stage", "text"}]}` document. The compiler checks current canonical
narrative/quest/scene/cast proof and the exact replayed quest session. A clue
cannot reveal a future spoiler, cannot bind an unknown scene, and cannot
change immutable source. The prompt is a deterministic source extraction,
not a claim of generative model inference or independently observed evidence.

Use `python -m scripts.studio_clue_visibility_cli --project
studio_arena_fighting_glacial_fjord --expected-source <canon-digest>
--prompt "build a source-bound clue trail"` to inspect the typed proposal.
Use `--authoring <json>` to compile an edited proposal, `--publish
<existing-private-directory>` to persist it without overwrite, and
`--restore <directory>` to reopen only a canonically replayable receipt.
The operator is responsible for directory custody and access authorization.
`--handoff-manifest yes` compiles a deterministic ZIP in memory containing
the canonical playable HTML quest and separately typed visible clue data.
The CLI reports its digest/manifest without writing the ZIP unless
\`--publish-playable <existing-private-directory>\` is supplied. The ZIP
contains the interactive canonical quest, a static accessible clue journal
showing only already-unlocked clues, and the typed clue JSON handoff. A
content-security policy prevents external scripts/styles. The ZIP is published
without overwrite and fsynced before the publication receipt is returned.

The HTML quest is genuinely interactive; the clue data is **not** yet
integrated into native engine clue UI. Hidden clue text is excluded from the
public handoff. This does not prove native game functionality, originality
rights, model inference, or consumer release readiness.

Verification: `pytest -q tests/test_studio_ecosystem_clue_visibility.py`,
then architecture, construction, capability, provider and enterprise gates,
then final-head CI. Reject pending/skipped/cancelled checks as evidence.
Rollback is removal of the opt-in adapter and authored receipt; canonical
source is unchanged. Maximum 64 clues, 64 quest actions, bounded canonical
request/receipt and no external network calls.

## Private offline editing

Supply `--editor-directory <private-existing-dir>` with a compiled prompt
or authoring request to publish a CSP-hashed accessible HTML editor. It
renders only operator-authorized source-replayed authoring, with editable
textareas and a JSON export button. No browser network or provider access.
Reimport with `--import-authoring <private-export.json>` and
`--baseline-authoring <exact-original-authoring-json>`. The export must be
owner-private (0600 on POSIX) and the containing directory private. The
import binds project, canonical source, quest session and baseline receipt
digest; the resulting edited authoring must pass the full canonical compiler
before any durable publication or playable handoff. Hidden clues are
operator-visible in this private editor, never in public player handoffs.
