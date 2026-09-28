export function now() { return Date.now(); }
export function hash32(s) {
  let h = 2166136261 >>> 0;
  const str = String(s ?? "");
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
export function estimateTokens(text) { return Math.ceil(String(text || "").length / 4); }
