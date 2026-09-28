function hash32(s) {
  let h = 2166136261 >>> 0;
  const str = String(s ?? "");
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
export function createConstantState(options = {}) {
  const dim = options.dim || 64;
  const state = new Float64Array(dim);
  let writes = 0;
  let fingerprint = "0";
  function absorb(text, weight = 1) {
    const s = String(text || "");
    const w = Math.max(0, Math.min(1, weight));
    for (let i = 0; i < s.length; i++) {
      const h = hash32(s[i] + ":" + i + ":" + writes);
      const idx = h % dim;
      const sign = h & 1 ? 1 : -1;
      state[idx] = state[idx] * 0.995 + sign * w * ((h % 1000) / 1000);
    }
    writes++;
    fingerprint = hash32(Array.from(state).map((x) => x.toFixed(4)).join(",")).toString(16);
    return fingerprint;
  }
  function inject() {
    return { dim, fingerprint, writes, vector: new Float64Array(state) };
  }
  function snapshot() {
    return { dim, writes, fingerprint };
  }
  return { absorb, inject, snapshot };
}
export default createConstantState;
