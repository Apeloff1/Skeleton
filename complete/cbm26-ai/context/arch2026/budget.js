export function createContextBudget(options = {}) {
  const maxTokens = options.maxTokens || 32000;
  const reserve = options.reserve || 2000;
  let used = 0;
  const items = [];

  function estimateTokens(text) {
    return Math.ceil(String(text || "").length / 4);
  }

  function add(item) {
    const tokens = item.tokens ?? estimateTokens(item.text);
    const row = {
      id: item.id || "c_" + items.length,
      tokens,
      tier: item.tier || "working",
      priority: item.priority ?? 0.5,
      text: item.text,
      offloaded: false,
    };
    items.push(row);
    used += tokens;
    compact();
    return row;
  }

  function compact() {
    const limit = maxTokens - reserve;
    if (used <= limit) return { compacted: false, used, limit };
    items.sort((a, b) => a.priority - b.priority);
    const actions = [];
    for (const it of items) {
      if (used <= limit) break;
      if (it.offloaded) continue;
      if (it.tier === "working" && it.priority < 0.4) {
        used -= it.tokens;
        it.offloaded = true;
        it.policy = "offload";
        actions.push({ id: it.id, policy: "offload" });
      }
    }
    return { compacted: actions.length > 0, actions, used, limit };
  }

  function activeContext() {
    return items.filter((i) => !i.offloaded).sort((a, b) => b.priority - a.priority);
  }

  function snapshot() {
    return {
      maxTokens,
      used,
      reserve,
      utilization: used / maxTokens,
      active: items.filter((i) => !i.offloaded).length,
      offloaded: items.filter((i) => i.offloaded).length,
    };
  }

  return { add, compact, activeContext, snapshot, estimateTokens };
}

export default createContextBudget;
