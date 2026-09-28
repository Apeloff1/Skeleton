function clamp01(n) {
  return Math.max(0, Math.min(1, Number(n) || 0));
}

export function createEvolvingPolicy(options = {}) {
  const lr = options.lr ?? 0.08;
  const table = new Map();
  const log = [];
  const key = (action, tier) => action + "::" + (tier || "*");
  function expect(action, tier) {
    const row = table.get(key(action, tier));
    return row ? row.value : 0.5;
  }
  function update(action, tier, reward) {
    const k = key(action, tier);
    const row = table.get(k) || { n: 0, value: 0.5 };
    row.n++;
    row.value = row.value * (1 - lr) + clamp01(reward) * lr;
    table.set(k, row);
    log.push({ at: Date.now(), action, tier, reward, value: row.value });
    if (log.length > 400) log.shift();
    return row;
  }
  function decide(record) {
    const tier = record.tier || "episodic";
    const importance = record.importance ?? 0.5;
    const hits = record.hits || 0;
    const candidates = [
      { action: "keep", score: expect("keep", tier) * 0.4 + importance * 0.35 },
      { action: "consolidate", score: expect("consolidate", tier) * 0.4 + (hits > 1 ? 0.25 : 0.05) },
      { action: "skillize", score: expect("skillize", tier) * 0.35 + (record.skill ? 0.4 : 0.05) },
      { action: "drop", score: expect("drop", tier) * 0.3 + (1 - importance) * 0.3 },
    ];
    candidates.sort((a, b) => b.score - a.score);
    return { choice: candidates[0].action, scores: candidates };
  }
  function snapshot() {
    return { size: table.size, recent: log.slice(-8) };
  }
  return { expect, update, decide, snapshot };
}

export default createEvolvingPolicy;
