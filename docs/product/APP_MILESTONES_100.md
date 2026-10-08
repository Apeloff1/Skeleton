# 100 App Milestones — User Journey Delivery

Tracked against the existing `frontend/` product shell. Focus: connected user outcomes, not LOC or standalone scaffolds. Milestones M001–M040 are implementation work in this PR; boxes mark code delivered to the branch, **not** release acceptance. No milestones beyond M040 are claimed complete. All milestones require exact-head build/CI plus live-device and backend integration review before release sign-off.

## Batch 1: Start & navigation

- [x] M001 — Guided journey hub (implemented in journey workspace; verification pending CI)
- [x] M002 — Product-home workflow entry (implemented in journey workspace; verification pending CI)
- [x] M003 — Search workflows by goal (implemented in journey workspace; verification pending CI)
- [x] M004 — Choose a workflow (implemented in journey workspace; verification pending CI)
- [x] M005 — Resume last opened step (implemented in journey workspace; verification pending CI)
- [x] M006 — Persist navigation-only history (implemented in journey workspace; verification pending CI)
- [x] M007 — Reset history safely (implemented in journey workspace; verification pending CI)
- [x] M008 — Context handoff Studio ↔ journeys (implemented in journey workspace; verification pending CI)
- [x] M009 — Context handoff knowledge ↔ journeys (implemented in journey workspace; verification pending CI)
- [x] M010 — Bounded recent-build picker (implemented in journey workspace; verification pending CI)

## Batch 2: Build reliability & export

- [x] M011 — Distinguish queued, running, done and failed asynchronous build jobs (implemented; verification pending CI)
- [x] M012 — Poll one job request at a time without overlapping intervals (implemented; verification pending CI)
- [x] M013 — Bound build observation and show truthful timeout recovery (implemented; verification pending CI)
- [x] M014 — Stop client monitoring on build navigation without cancelling server work (implemented; verification pending CI)
- [x] M015 — Show build-stage and refinement errors with refresh/retry controls (implemented; verification pending CI)
- [x] M016 — Re-fetch actual stages after mounting an empty build (implemented; verification pending CI)
- [x] M017 — Prevent a failed skip/refinement from looking successful (implemented; verification pending CI)
- [x] M018 — Open this build's knowledge base directly from Studio (implemented; verification pending CI)
- [x] M019 — Navigate to a build-specific ZIP workflow rather than assuming download success (implemented; verification pending CI)
- [x] M020 — Reject missing/demo export targets and expose packaging/download failure (implemented; verification pending CI)

## Batch 3: Game knowledge reliability & contextual editing

- [x] M021 — Require a real selected build before reading knowledge (implemented; verification pending CI)
- [x] M022 — Replace infinite initial-loading spinner with a recoverable error screen (implemented; verification pending CI)
- [x] M023 — Keep last successfully read artifacts visible with a stale-response warning (implemented; verification pending CI)
- [x] M024 — Reject null, arrays and non-object JSON edits before submitting (implemented; verification pending CI)
- [x] M025 — Report actual backend approval failures instead of silently ignoring them (implemented; verification pending CI)
- [x] M026 — Prevent overlapping knowledge mutation jobs across forge/refine/apply (implemented; verification pending CI)
- [x] M027 — Resolve refine operations only on terminal verified job status (implemented; verification pending CI)
- [x] M028 — Show truthful knowledge-to-game sync outcome or timeout (implemented; verification pending CI)
- [x] M029 — Track forge jobs with bounded, cancellable client observation (implemented; verification pending CI)
- [x] M030 — Continue the same game between KB and Studio with contextual navigation (implemented; verification pending CI)

## Batch 4: Project-scoped world-building workbench

- [x] M031 — Open a single, project-scoped world workbench with a real game ID (implemented; verification pending CI)
- [x] M032 — Inspect server-confirmed world, narrative, mechanics and asset pipeline evidence (implemented; verification pending CI)
- [x] M033 — Preview grounded artifact content without duplicating backend authority (implemented; verification pending CI)
- [x] M034 — Forge or re-forge a selected world knowledge stage with actual job monitoring (implemented; verification pending CI)
- [x] M035 — Inspect actual mounted systems for the selected build (implemented; verification pending CI)
- [x] M036 — Inspect whether asset-generation context can be read for that game (implemented; verification pending CI)
- [x] M037 — Open Scene Composer with a real game ID, never the demo project by default (implemented; verification pending CI)
- [x] M038 — Prioritize current game when selecting Worldforge source (implemented; verification pending CI)
- [x] M039 — Pass correctly named game/build/pid parameters across seven creative tools (implemented; verification pending CI)
- [x] M040 — Return from world tools to the same Studio game and browse all saved worlds without false project filtering (implemented; verification pending CI)

## Batch 5: AI copilot

- [ ] M041 — Open assistant workspace
- [ ] M042 — Attach project context
- [ ] M043 — Request design advice
- [ ] M044 — Review tool execution proposal
- [ ] M045 — Approve governed action
- [ ] M046 — Inspect evidence citations
- [ ] M047 — Compare candidate responses
- [ ] M048 — Handle offline AI error
- [ ] M049 — Resume interrupted AI turn
- [ ] M050 — Export verified decision

## Batch 6: Editor & collaboration

- [ ] M051 — Open working project file
- [ ] M052 — Edit code with preview
- [ ] M053 — Inspect compile errors inline
- [ ] M054 — Review diff before applying
- [ ] M055 — Undo prior edit
- [ ] M056 — Restore version
- [ ] M057 — Invite collaborator
- [ ] M058 — Show review comments
- [ ] M059 — Resolve conflicts
- [ ] M060 — Track review approvals

## Batch 7: Play & test

- [ ] M061 — Launch current playable
- [ ] M062 — Stream runtime logs
- [ ] M063 — Inspect controls tutorial
- [ ] M064 — Save play session
- [ ] M065 — Resume play session
- [ ] M066 — Record gameplay feedback
- [ ] M067 — Trace crash to build step
- [ ] M068 — Compare performance profiles
- [ ] M069 — Inspect accessibility behavior
- [ ] M070 — Replay regression case

## Batch 8: Quality & release

- [ ] M071 — Run build QA
- [ ] M072 — Review QA failures
- [ ] M073 — Refine one stage
- [ ] M074 — Inspect artifact lineage
- [ ] M075 — Compare render variants
- [ ] M076 — Inspect package contents
- [ ] M077 — Build signed package
- [ ] M078 — Review release checklist
- [ ] M079 — Export distribution artifact
- [ ] M080 — Restore prior release

## Batch 9: Operate & recover

- [ ] M081 — Inspect live runtime health
- [ ] M082 — Understand degraded mode
- [ ] M083 — Inspect queue pressure
- [ ] M084 — Review agent executions
- [ ] M085 — Cancel active operation
- [ ] M086 — Retry safe failed operation
- [ ] M087 — Open startup diagnostics
- [ ] M088 — Enter fallback mode
- [ ] M089 — Recover saved project
- [ ] M090 — Review audit events

## Batch 10: Polish & personalization

- [ ] M091 — Adaptive compact layout
- [ ] M092 — Full keyboard workflow
- [ ] M093 — Screenreader labels audit
- [ ] M094 — Reduced motion support
- [ ] M095 — Offline guidance per route
- [ ] M096 — Localized journey copy
- [ ] M097 — Favorite tools
- [ ] M098 — Recent task timeline
- [ ] M099 — Per-project workspace view
- [ ] M100 — End-to-end guided acceptance session

## Delivery policy

- Keep the canonical product shell `/product`; no competing application entry point.
- Preserve game ID and context across routes without putting private project contents into generic local preferences.
- An opened screen is not the same as a completed task; authoritative build/AI state comes from existing services.
- Each batch must result in usable, navigable behavior. If a backend endpoint is unavailable, show a recoverable state rather than a fake success.
- Promote a batch only after mobile + web checks and relevant user-journey validation.
