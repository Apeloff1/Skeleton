# BOT BRIEF — Skeleton factory (2026-10-24)

## Rules
- Local clone on the box, feature branch per unit, local tests are the gate, PRs open as DRAFT; nothing merges this push (later: fully green + Jenkins approval where required). No Cursor cloud agents.
- Push with `gh` or GitHub MCP. Never print tokens. Shared `Apeloff1` token: **sign every commit body with `Unit: Uxx  Owner: <bot>`** so pushes are attributable.
- Never push to a branch you don't own. Never stack PRs onto a starved Actions queue (>100 queued: hold remote pushes, keep building locally).
- Extend-only, hexagonal boundaries, mirrors (`skeleton/ai/**`) stay byte-identical with sources.
- Don't contact BB (principal). Escalate to Chief of Staff / Grok Bot.

## Lane map (#807 lanes + issue lanes)
| #807 lane | Batches | Owner |
|---|---|---|
| build | B001–B010 | Grenn (CI/build) |
| creator | B011–B020 | Frontend (Studio UI) |
| gameplay | B021–B030 | Murash (economy slice claimed: `murash/economy-inventory-currency-sinks` — inventory, currency, faucet, sink, tests; B026/B029) |
| ai | B031–B040 | Olly |
| world | B041–B050 | Santo |
| assets | B051–B060 | Bork |
| network | B061–B070 | Walt |
| quality | B071–B080 | Gronk |
| security | B081–B090 | Internal Systems (review: Jenkins) |
| platform | B091–B100 | Snappo (Godot adapter/packs) |
Dispatch Manager rebuilds the batch list and hands unclaimed batches to idle bots. Throughput Delegator owns the PR queue. Issues: #4133 Glenny, #4138 Klint (plan only), #4122 Coder Lead, #4167 Santo, #4168 Bork, #4169 Olly, #4170 Gronk, #3721 Wally, #80 Carrol, CI lanes/#4137 Grenn.

## Work-unit format
```
Uxx | title | source (#issue / Bxxx) | owner | branch | files | acceptance | local gate cmd | deps | size
```

## Claim protocol
Ask CoS → CoS writes owner into `artifacts/COS/FANOUT.md` → you add row `claimed` in `STATUS.md` → states: `claimed → local-green → pr-open → merged` (or `blocked: <reason>`). Release claims you drop.

## Definition of done
Acceptance criteria met · draft PR open · focused tests + relevant gates green locally · mirrors/traceability regenerated · PR open with `Closes/Refs` and test evidence · green Merge Readiness · merged · STATUS.md updated with PR + merge SHA. Deterministic scaffolding is never reported as model inference or production qualification.

## Never this push
Deletes, force-push, branch-protection or secret changes, external posts, merges.

## Ask before (via CoS; CoS goes via Grok Bot, never BB directly)
Deletes/retirements of data or modules · force-push / history rewrite · anything costing money (runners, plans, APIs, checkpoints) · external posts or messages as BB · secrets, tokens, permissions, branch protection, admin settings · model weights/licence decisions.
