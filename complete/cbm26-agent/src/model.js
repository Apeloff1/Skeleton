import { createWorkingMemory } from "./working_memory.js";
import { createStore } from "./store.js";
import { createRetriever } from "./retrieve.js";
import { createPlanner } from "./plan.js";
import { createEval } from "./eval.js";

export function createCBM26(options = {}) {
  const wm = createWorkingMemory(options.wm);
  const store = createStore();
  const retriever = createRetriever();
  const planner = createPlanner();
  const ev = createEval();
  let ai = null;

  async function attachAI() {
    if (ai) return ai;
    try {
      const { createIntegratedAI } = await import("../../cbm26-ai/src/index.js");
      ai = await createIntegratedAI(options.ai || {});
    } catch {
      ai = null;
    }
    return ai;
  }

  async function turn(input) {
    const t0 = Date.now();
    const decision = planner.plan(input, { storeCount: store.snapshot().count });
    wm.push("user", input);
    let reply = decision.say || "";
    if (decision.action === "remember") {
      await store.append({ kind: "note", text: decision.content || input });
      reply = "Noted.";
    } else if (decision.action === "retrieve" || decision.action === "retrieve_then_respond") {
      const hits = retriever.score(decision.query || input, await store.all());
      reply = hits[0] ? hits[0].doc.text : "Nothing stored yet.";
    } else if (decision.action === "reflect") {
      reply = JSON.stringify({ wm: wm.snapshot(), store: store.snapshot(), eval: ev.summary() });
    }
    if (!reply || decision.action === "respond" || decision.action === "retrieve_then_respond") {
      const sys = await attachAI();
      if (sys?.turn) {
        const out = await sys.turn(wm.contextText() + "\nuser: " + input);
        reply = out.text || reply || String(out);
      } else if (!reply) {
        reply = "Ready. Context is RAM. Store is disk.";
      }
    }
    wm.push("assistant", reply);
    const ms = Date.now() - t0;
    ev.record({ action: decision.action, ms });
    return { reply, decision, ms };
  }

  function snapshot() {
    return { wm: wm.snapshot(), store: store.snapshot(), eval: ev.summary(), ai: ai?.snapshot?.() || null };
  }

  return { turn, snapshot, wm, store, planner };
}
export default createCBM26;
