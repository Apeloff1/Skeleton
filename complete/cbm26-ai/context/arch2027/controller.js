import { createContextArchitecture } from "../arch2026/index.js";
import { createEvolvingPolicy } from "./evolving_policy.js";
import { createSkillRegistry } from "./skills.js";
import { createConstantState } from "./constant_state.js";
import { createMemoryEval } from "./eval_probes.js";

export function createContext2027(options = {}) {
  const base = createContextArchitecture(options);
  const policy = createEvolvingPolicy(options.policy || {});
  const skills = createSkillRegistry();
  const state = createConstantState({ dim: options.stateDim || 64 });
  const eval_ = createMemoryEval();
  let ticks = 0;

  function ingest(text, meta = {}) {
    ticks++;
    const raw = typeof text === "object" ? text.text || JSON.stringify(text) : String(text);
    if (state.absorb) state.absorb(raw, meta.importance ?? 0.5);
    const out = base.ingest(raw, meta);
    const decision = policy.decide
      ? policy.decide({ tier: out.row?.tier, importance: out.row?.importance, text: raw })
      : { choice: "keep" };
    if (policy.update) policy.update(decision.choice || "keep", out.row?.tier, 0.55);
    return { ...out, decision, state: state.snapshot?.() };
  }

  function query(q, opts = {}) {
    const r = base.query(q, opts);
    const probe = eval_.probe ? eval_.probe({ memorySnap: r.memorySnap, queryHits: r.memory }) : null;
    return { ...r, probe, state: state.inject?.(), skills: skills.snapshot?.() };
  }

  function snapshot() {
    return {
      ticks,
      base: base.snapshot(),
      policy: policy.snapshot?.(),
      skills: skills.snapshot?.(),
      state: state.snapshot?.(),
    };
  }

  function warmStart() {
    return { state: state.inject?.(), skills: skills.snapshot?.(), memory: base.memory?.snapshot?.() };
  }

  return { ingest, query, snapshot, warmStart, base, policy, skills, state };
}

export default createContext2027;
