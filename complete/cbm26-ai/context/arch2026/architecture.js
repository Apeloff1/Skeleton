import { createMemoryTiers } from "./memory_tiers.js";
import { createSegmentConsolidator } from "./segment_consolidate.js";
import { createContextBudget } from "./budget.js";

export function createContextArchitecture(options = {}) {
  const memory = createMemoryTiers(options.memory);
  const segments = createSegmentConsolidator(options.segment);
  const budget = createContextBudget(options.budget);
  let turns = 0;

  function ingest(text, meta = {}) {
    const raw = typeof text === "object" ? text.text || JSON.stringify(text) : String(text);
    turns++;
    const seg = segments.observe ? segments.observe(raw, meta) : { finalized: null };
    const importance = meta.importance ?? 0.5;
    const tier = meta.tier || (turns < 3 ? "working" : "episodic");
    const row = memory.push
      ? memory.push(tier, { text: raw.slice(0, 4000), importance, ...meta })
      : { id: "row_" + turns, text: raw, tier, importance };
    if (budget.add) budget.add({ id: row.id, text: raw, tier, priority: importance });
    return { row, seg, budget: budget.snapshot?.() || null };
  }

  function query(q, opts = {}) {
    const memHits = memory.retrieve ? memory.retrieve(q, opts.budget || 10) : [];
    return {
      memory: memHits,
      ranked: memHits,
      budget: budget.snapshot?.() || null,
      memorySnap: memory.snapshot?.() || null,
      segments: segments.snapshot?.() || null,
    };
  }

  function snapshot() {
    return { turns, memory: memory.snapshot?.(), budget: budget.snapshot?.(), segments: segments.snapshot?.() };
  }

  return { ingest, query, snapshot, memory, segments, budget };
}

export default createContextArchitecture;
