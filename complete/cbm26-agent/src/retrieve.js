export function createRetriever() {
  function tokenize(text) {
    return String(text).toLowerCase().split(/[^a-z0-9åäö]+/i).filter((t) => t.length > 1);
  }
  function score(query, docs) {
    const q = tokenize(query);
    if (!q.length || !docs.length) return [];
    const N = docs.length;
    const df = new Map();
    const tfs = docs.map((d) => {
      const toks = tokenize(d.text || d.content || "");
      const tf = new Map();
      for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
      for (const t of new Set(toks)) df.set(t, (df.get(t) || 0) + 1);
      return { doc: d, tf, len: toks.length };
    });
    const avgLen = tfs.reduce((s, x) => s + x.len, 0) / N || 1;
    const k1 = 1.2, b = 0.75;
    return tfs.map(({ doc, tf, len }) => {
      let s = 0;
      for (const term of q) {
        const f = tf.get(term) || 0;
        if (!f) continue;
        const n = df.get(term) || 0;
        const idf = Math.log(1 + (N - n + 0.5) / (n + 0.5));
        s += idf * ((f * (k1 + 1)) / (f + k1 * (1 - b + b * (len / avgLen))));
      }
      return { doc, score: s };
    }).filter((x) => x.score > 0).sort((a, b) => b.score - a.score);
  }
  return { score, tokenize };
}
