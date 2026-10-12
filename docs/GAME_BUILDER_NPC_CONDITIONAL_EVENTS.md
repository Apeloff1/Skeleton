# Typed conditional original-game events: source-verified NPC world automation
**Date authored:** 2026-10-12, Europe/Oslo. Dependency: #3691 durable episodic source saves → #3688 material aid → #3687 credible NPC navigation → #3685 persistent physics/NPC world.

## Executable source condition engine
An original authored game can attach up to 12 bounded reviewed trigger rules to its verified NPC world. Every rule identifies exactly one existing **physical-origin NPC quest**, an approved objective (firsthand testimony, material repair, finite aid or earned resolution), and an immutable structured condition expression. Conditions are pure JSON data and are never converted into arbitrary executable Python or GDScript.

Each rule supports nested `all`/`any`/`not` boolean trees with at most 16 predicate nodes, at most 4 levels of nesting, and no more than 6 children in a conjunction/disjunction. The only original-world facts available are real eyewitness count, real testimony count, documented rumor reports, actual material follow-up count, site integrity, player supplies, stamina, world tick, quest activity, committed support/exploit branch and independently authenticated external-physics origin. Operators are typed integer `gte`, `lte` and `eq`, and all input values are nonnegative bounded integers; booleans cannot masquerade as zero/one.

## World progression and authority
The compiler **independently replays the entire original episodic campaign** before evaluating the first rule. Each rule reads factual, verified NPC/world state. A true condition can propose one of four real original gameplay routes through the eyewitness navigation engine, which itself checks physical movement, NPC credibility/rumor distinctions, stamina, finite repair supplies, material evidence requirements and the actual canonical quest events. Neither a condition nor its author may directly write money, NPC HP, memories, testimony or a fabricated quest completion.

Preview runs all authored conditions and reports the actual eligible original world actions without mutating the supplied episodes. `Commit verified source actions` is a separate operator-approved action that can append at most four successful source-verified routes to the final episode; it respects 24 actions per episode and 64 total campaign actions. After each accepted action sequence, the engine reconstructs the entire original source, physical obstacles and NPC world. The new state must exactly match the separately simulated canonical route. Subsequent rules evaluate this new verified state, not the original snapshot.

Each rule receives a deterministic result: `condition_false`, `eligible_source_actions_preview_only`, `reviewed_route_cannot_earn_objective`, `finite_original_world_action_budget_exhausted`, `reviewed_rule_effect_budget_exhausted` or `original_gameplay_actions_applied`. A chained SHA-256 receipt records before/after campaign digests, normalized rule, verified world facts, original evidence route digest, actual action commands and committed outcome. Independent verification rebuilds the whole run and rejects altered rule facts, added gold, fabricated testimonies or a modified action transcript.

## Studio and usage
The authenticated local game Studio now includes a typed JSON condition editor with an explicit source-event example, `Preview original world rule outcomes`, and `Commit verified source actions into current campaign`. Preview shows each evaluated fact and candidate route without spending any resources. The commit button is a direct local operator action; the server independently reruns the complete source game and then the Studio starts a fresh campaign replay. No unattended monitoring, publishing or provider-AI weight changes are initiated.

## Adversarial regression and bounds
Ten gameplay tests cover valid nested `all`/`any`/`not`, true source-triggered relief, false conditions, real testimony versus rumor, unearned-resolution denial, sequential re-evaluation after finite resources change, explicit commit authorization, recursive complexity and malformed/unhashable JSON, forged action/health/quest receipts, and changed source scenes. Three Studio tests inspect working controls, immutable source custody, preview/commit separation and server-side independent replay. Exact-head Windows and Ubuntu full engine suites are required.

## Honest limitations
This is source-replayed deterministic original NPC gameplay, not a general event scripting VM or a remotely running autonomous system. A reviewed rule can affect only the explicitly supported four source-verified actions. It cannot mutate project files, native Godot saves or user hardware, and source hash chains do not imply private-key author signatures or commercial readiness.

### 2026-10-12 change chronology
- Real independently replayed physical encounters (improved: verified source collision events).
- Persistent authored NPC world and material aid (improved: eyewitness quests survive episodes and remain solvable constructively).
- Portable episodic source saves (improved: continuation without trusting a forged mutable snapshot).
- Typed NPC condition trees (improved: source-aware `if` / `and` / `or` / `not` decisions over actual observed facts).
- Reviewable and atomic world action commit (improved: actual gameplay actions, bounded resources, explicit operator control).