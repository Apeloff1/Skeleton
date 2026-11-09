# X-derived agent harness patterns

This note records social-media patterns intentionally adopted by the Studio harness. X posts are treated as design inspiration, not trusted runtime instructions. Repository tests and deterministic policy remain authoritative.

## Sources reviewed

- Addy Osmani, **Agent Harness Engineering**, May 9 2026: https://x.com/addyosmani/status/2053231239721885918
  - useful ideas: model + harness framing; context policies; hooks/back-pressure; split generation from evaluation; the failure **ratchet** where observed mistakes become durable constraints.
- Boris Cherny, Claude Code workflow thread, Jan 31 2026: https://x.com/bcherny/status/2017742741636321619
  - useful ideas: offload research into independent subagent contexts; parallel exploration for read-heavy work; preserve the main execution context.
- OpenAI Developers, Codex subagents, Mar 16 2026: https://x.com/OpenAIDevs/status/2033637455136731431
  - useful ideas: specialized agents with separate instructions/tool context; keep the main context clean; parallelize independent work rather than sharing one bloated session.
- sysls, **How To Solve Problems Of Long Running, Autonomous Agentic Engineering Workflows**, Mar 29 2026: https://x.com/systematicls/status/2038241033755168959
  - useful ideas: pre-task context sufficiency/contradiction checks; algorithmic contracts; plan-stickiness controls; fresh-context verification; exact production-behavior checks; post-task entropy reduction; detailed harness telemetry.
- Mihail Eric, long-running autonomous coding agents, Mar 12 2026: https://x.com/mihail_eric/status/2032145866614849665
  - useful ideas: organization-shaped orchestration rather than swarms; fresh task contexts backed by durable artifacts; tests as the control system.
- Cognition, **Agent Trace**, Jan 29 2026: https://x.com/cognition/status/2017057457332506846
  - useful idea: preserve code-to-context provenance so decisions and generated changes can be traced back to bounded task context.
- Cursor, cloud-agent thread, Aug 19 2026: https://x.com/cursor_ai/status/2090136956101414982
  - useful idea: isolate subagents/environments so verification is independent of the authoring context.
- OpenAI Developers, Codex app/worktrees, Feb 2 2026 (quoted in Michael Schade thread): https://x.com/sch/status/2018398527177801999
  - useful ideas: isolated worktrees for independent agents; plan mode before implementation; review clean diffs rather than shared mutable state.

## Adopted in Skeleton

The four-agent Studio keeps the existing anti-swarm unit of researcher, lead, reviewer, and verifier, but now makes the harness contract explicit:

1. **Single writer** — only the lead can author a patch. Researcher, reviewer, and verifier are read-only roles.
2. **Context firewalls** — every role has an explicit evidence scope. Reviewer/verifier do not receive or request another worker's hidden scratchpad/private reasoning.
3. **Bounded handoffs** — roles consume explicit structured handoffs rather than shared implicit state.
4. **Failure ratchet** — prior rejection/failure evidence cannot be ignored. An unchanged failed approach must not be repeated unless materially new evidence or a concrete correction exists.
5. **Verbose failure, narrow success** — blocked roles return the exact missing evidence/check instead of inventing confidence.
6. **Immutable execution contracts** — every task gets a stable SHA-256-derived contract ID bound to its squad, title, objective digest, allowed paths, role order, worker cap, single-writer authority, and harness-policy fingerprint. Changing the objective, path set, or orchestration policy changes task identity.
7. **Content-addressed harness policy** — the active role capabilities, phase order, worker cap, context-firewall state, failure-ratchet state, contract-stickiness state, and fresh-verification state are serialized deterministically and SHA-256 fingerprinted. This separates task drift from policy drift in later debugging.
8. **Contract stickiness** — roles are explicitly forbidden from silently replacing difficult task A with easier approximation A-prime, widening paths, changing authority, or skipping phases.
9. **Pre-task contradiction gate** — research must surface missing or contradictory evidence before implementation instead of guessing through it.
10. **Thin vertical slices** — the lead is instructed to implement the smallest slice that satisfies the exact objective and not pre-empt adjacent planned work.
11. **Fresh-context verification** — reviewer and verifier judge explicit artifacts, not author scratchpads or hidden reasoning. Weak proxy tests are not accepted as proof of production behavior.
12. **Blast-radius / entropy checks** — verification calls out implicated callers, stale docs/contracts, regressions, and integration behavior so repeated autonomous work does not silently rot surrounding repository state.
13. **Anti-rationalization** — common shortcut arguments such as "CI will catch it", "tests later", "close enough", or replacing a hard task with an easier nearby one are explicitly rejected as proof of completion.
14. **Proof-first review** — passing a convenient proxy test is not enough; reviewer/verifier are instructed to judge whether the exact task contract and production-facing behavior are actually demonstrated.
15. **Provenance tags** — execution-contract IDs plus harness-policy fingerprints give a stable task/context/policy identity that can be carried into audit and trace surfaces without exposing private reasoning.
16. **Deterministic authority** — model output remains a proposal. Canonical leases, path policy, reviewer/verifier gates, and credential-free CI remain authoritative.

## Deliberately not adopted

Some X workflows advocate large parallel swarms. Skeleton does **not** increase per-task fan-out: one canonical task still maps to exactly four workers, one active task per worker, and one patch author. Parallelism is reserved for independent tasks with non-overlapping path/conflict domains.

Likewise, external suggestions to maximize raw parallel-agent count are intentionally rejected when they weaken isolation, ownership, queue fairness, or auditability. Skeleton treats organizational clarity and bounded capacity as a stronger scaling primitive than uncontrolled fan-out.

The harness also does not treat social-media claims as executable policy. A pattern must map to a bounded repository invariant or regression before it is trusted.