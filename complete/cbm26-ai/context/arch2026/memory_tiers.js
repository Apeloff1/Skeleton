export const TIERS = Object.freeze(["working", "episodic", "semantic", "procedural"]);

function clamp01(n) {
  return Math.max(0, Math.min(1, Number(n) || 0));
}

export function createMemoryTiers(options = {}) {
  const limits = {
    working: options.workingLimit || 64,
    episodic: options.episodicLimit || 512,
    semantic: options.semanticLimit || 1024,
    procedural: options.proceduralLimit || 256,
  };
  const stores = { working: [], episodic: [], semantic: [], procedural: [] };
  let seq = 0;

  function push(tier, record) {
    if (!stores[tier]) tier = "episodic";
    const row = {
      id: "m_" + ++seq,
      tier,
      at: Date.now(),
      hits: 0,
      importance: clamp01(record.importance ?? 0.5),
      ...record,
    };
    stores[tier].push(row);
    while (stores[tier].length > limits[tier]) {
      stores[tier].sort((a, b) => a.importance - b.importance);
      stores[tier].shift();
    }
    return row;
  }

  function retrieve(query, budget = 12) {
    const q = String(query || "").toLowerCase();
    const scored = [];
    for (const t of TIERS) {
      for (const r of stores[t]) {
        const hay = (r.text || r.title || "").toLowerCase();
        let s = r.importance * 0.4;
        if (q && hay.includes(q)) s += 0.4;
        if (t === "working") s += 0.15;
        scored.push({ ...r, score: s });
      }
    }
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, budget);
  }

  function snapshot() {
    const counts = {};
    for (const t of TIERS) counts[t] = stores[t].length;
    return { counts, limits, total: TIERS.reduce((s, t) => s + stores[t].length, 0) };
  }

  function promoteWorkingToEpisodic(minImportance = 0.4) {
    const keep = [];
    for (const r of stores.working) {
      if (r.importance >= minImportance || r.hits > 2) {
        stores.episodic.push({ ...r, tier: "episodic" });
      } else keep.push(r);
    }
    stores.working = keep;
    return true;
  }

  return { push, retrieve, snapshot, stores, promoteWorkingToEpisodic };
}

export default createMemoryTiers;
