# Jeeves project workbench

Open `/jeeves-workbench`, or choose **Workbench** in Jeeves chat. The workbench
adds a project workspace to the conversation baseline and works without an AI
provider. Projects and records live on the current device; they are not synced
to an account or server.

## Workflows

- Create a project with a goal, engine, background, target date and weekly budget.
- Plan tasks with priority, estimates, deadlines, checklists, note links and
  prerequisite tasks. Completing a task requires finished prerequisites and
  checklist items. Session planning fits available tasks into a time budget and
  explicitly labels unestimated work.
- Record notes, decisions, experiments and retrospectives. Link sources and
  related notes; inspect backlinks. Confidence is a user annotation, not an AI
  verification result. Source URLs allow only HTTP(S) without embedded credentials.
- Turn notes into study cards. Reveal the answer, grade it and schedule the next
  review. New/learning/review/relearning/suspended states, daily limits, review
  history, lapse counts and latest-review undo are supported. This deterministic
  scheduler does not claim calibrated recall probability or measured mastery.
- Run one focus session at a time, optionally attached to an available task.
  Pause/resume excludes paused time. Finishing a session records a reflection;
  it does not complete the task. No notifications or background service is used.
- Save and edit reusable prompts with explicit variables. Bundled templates are
  opt-in. Variable expansion is one pass, bounded, and reports missing fields.
- Search across projects with quoted phrases, exclusions, `tag:`, `type:` and
  `status:` filters. Search results open the corresponding project collection.
- Review weekly progress, focus reflections, self-assessed study grades, current
  blockers, stale work and evidence gaps. Save a retrospective or export Markdown.
- Select and preview project context before opening an unsent chat draft.
  Context is limited to 4,000 characters, with omissions and shortened sections
  shown. The chat is separate from existing drafts. Nothing is sent automatically.
- Save completed chat messages into a project notebook. Captures retain a
  conversation source and are marked unverified. Duplicate unchanged captures
  in the same project reuse the existing note.

## Storage, recovery and portability

`WORKBENCH_KEY`, `RECOVERY_KEY` and `HANDOFF_KEY` are versioned local storage keys
defined in `frontend/features/Jeeves/workbench/types.ts`. The shared store has
ordered, coalesced saves, observable save state, explicit retry, a prior valid
saved snapshot, and bounded in-memory undo/redo. Corrupt saved data is left intact.
An invalid current snapshot is never copied over a valid recovery snapshot.

Before saving, the store compares the currently stored value with its last known
value. A detected other-tab edit blocks further changes and offers export/reload.
This is advisory conflict detection: storage does not provide an atomic
compare-and-swap, so use one editing tab at a time. Undo history is session-local;
it restores content while advancing entity revisions to reject stale editors.

Export full or single-project JSON backups, Markdown reports, task/card CSV,
study guides, source bibliographies or focus history. JSON import validates both
field schemas and cross-record relationships. Merge creates separate IDs and
remaps links; replace restores the imported contents while retaining the local
workspace identity. Imported running timers become abandoned at the last
evidenced timestamp. A first-run backup importer is available before any project
exists. JSON backups do not include the separate chat workspace or attachment bytes.

Pasted task lists, task CSV, card TSV and Markdown notes support a preview followed
by an atomic import. Invalid rows prevent the entire batch. CSV parsing handles
quoted multiline fields and escaped quotes. CSV exports neutralize spreadsheet
formula prefixes. Card intake deliberately starts fresh scheduling rather than
trusting third-party scheduling fields.

Limits are explicit: 40 projects, 1,500 tasks, 800 notes, 500 sources, 2,000 cards,
200 prompts, 500 focus sessions, 5,000 retained review rows and 1,500 activity
events. Total encoded workbench content is capped at five million characters;
backup files are capped at 12 MiB. Entity capacity failures do not silently evict
records. Task/note/source/card libraries render pages of 30 items; exports and
filters still operate on the complete collection. Retained-history limits and
record deletion affect reported historical totals.

## Implementation and verification

Pure TypeScript modules handle commands, validation, graph planning, scheduling,
search, intake, context, capture, analytics and backup. React Native/Expo screens
use the same command layer. The store accepts injected storage, clock and ID
generation for deterministic failure and concurrency testing.

From `frontend`:

```sh
npm run typecheck:jeeves
npm run test:jeeves
npx eslint features/Jeeves app/jeeves-workbench.tsx app/jeeves-chat.tsx --max-warnings=0
```

The tests include immutable graph mutations, import/citation integrity, storage
failure and recovery, delayed saves, other-tab conflicts, stale editor revisions,
clock rollback, scheduler transitions, local calendar boundaries, CSV parsing,
formula neutralization, bounded context, prompt interpolation, pagination, capture
deduplication, durable chat handoff receipts, and complete project workflows.

Validation for this follow-up: 223 frontend tests and 29 backend tests passed;
focused TypeScript and ESLint passed. An isolated Expo Router web preview verified
project and task creation, saved state after reload, an unsent project chat draft
with attached context, card creation/reveal/grading, and the weekly review view.
The follow-up adds 9,134 physical implementation/test lines (9,133 net), measured
against baseline commit `2fba6df`; documentation and generated files are excluded.

The original 29 backend HTTP tests remain available with:

```sh
python -m pytest tests/test_jeeves_chat_workspace.py -q
```

The full application still has a pre-existing Windows case collision between
`frontend/components/UI` and `frontend/components/ui`. Focused Jeeves TypeScript,
lint, tests and an isolated Expo Router preview exercise the changed code without
claiming a full-app build passes. Native-device sharing/picker flows, live provider
generation and account synchronization are outside this validation.
