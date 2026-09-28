import { estimateTokens, now } from "./util.js";
export function createWorkingMemory(options = {}) {
  const maxTokens = options.maxTokens ?? 4096;
  const items = [];
  let seq = 0;
  function totalTokens() { return items.reduce((s, x) => s + x.tokens, 0); }
  function evict() {
    while (totalTokens() > maxTokens) {
      const idx = items.findIndex((x) => !x.pin);
      if (idx < 0) break;
      items.splice(idx, 1);
    }
  }
  function push(role, text, opts = {}) {
    const row = { id: "wm_" + ++seq, role, text: String(text).slice(0, 8000), tokens: estimateTokens(text), at: now(), pin: !!opts.pin };
    items.push(row);
    evict();
    return row;
  }
  function snapshot() {
    return { maxTokens, usedTokens: totalTokens(), count: items.length };
  }
  function contextText() {
    return items.map((x) => `${x.role}: ${x.text}`).join("\n");
  }
  return { push, snapshot, contextText, totalTokens, get items() { return items.slice(); } };
}
