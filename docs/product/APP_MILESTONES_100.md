# 100 App Milestones — User Journey Delivery

Tracked against the existing `frontend/` product shell. Focus: connected user outcomes, not LOC or standalone scaffolds. Milestones M001–M010 are implementation work in this PR; boxes mark code delivered to the branch, **not** release acceptance. No milestones beyond M010 are claimed complete. All milestones require exact-head build/CI plus live-device and backend integration review before release sign-off.

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

## Batch 2: Create & build

- [ ] M011 — Create project from natural-language brief
- [ ] M012 — Edit game vision and constraints
- [ ] M013 — Validate design questionnaire
- [ ] M014 — Select era and platform
- [ ] M015 — Visualize build phase plan
- [ ] M016 — Execute a single phase
- [ ] M017 — Pause active phase
- [ ] M018 — Resume interrupted phase
- [ ] M019 — Review phase diagnostics
- [ ] M020 — Version build assets

## Batch 3: Knowledge & acquisition

- [ ] M021 — Search authoritative references
- [ ] M022 — Inspect acquisition provenance
- [ ] M023 — Import permitted source
- [ ] M024 — View confidence for extracted claims
- [ ] M025 — Compare conflicting claims
- [ ] M026 — Tag game mechanics examples
- [ ] M027 — Attach knowledge to project
- [ ] M028 — Revalidate stale sources
- [ ] M029 — Review knowledge graph links
- [ ] M030 — Approve knowledge revisions

## Batch 4: World & design

- [ ] M031 — Create world graph
- [ ] M032 — Edit scene hierarchy
- [ ] M033 — Preview lighting
- [ ] M034 — Place and inspect entities
- [ ] M035 — Design quests
- [ ] M036 — Design economy
- [ ] M037 — Design NPC behavior
- [ ] M038 — Tune character progression
- [ ] M039 — Inspect simulation constraints
- [ ] M040 — Export portable world data

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
