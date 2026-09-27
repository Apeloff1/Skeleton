export function createCharNgram(order = 8) {
  const counts = new Map();
  const totals = new Map();
  let trained = false;
  function train(text) {
    const s = String(text);
    for (let i = 0; i < s.length; i++) {
      for (let o = 1; o <= order; o++) {
        if (i - o < 0) continue;
        const ctx = s.slice(i - o, i);
        const ch = s[i];
        if (!counts.has(ctx)) counts.set(ctx, new Map());
        const m = counts.get(ctx);
        m.set(ch, (m.get(ch) || 0) + 1);
        totals.set(ctx, (totals.get(ctx) || 0) + 1);
      }
    }
    trained = true;
    return { contexts: counts.size };
  }
  function nextDist(context) {
    for (let o = Math.min(order, context.length); o >= 1; o--) {
      const ctx = context.slice(-o);
      if (counts.has(ctx)) {
        const m = counts.get(ctx);
        const tot = totals.get(ctx) || 1;
        const entries = [...m.entries()].map(([ch, n]) => ({ ch, p: n / tot }));
        entries.sort((a, b) => b.p - a.p);
        return entries;
      }
    }
    return [{ ch: " ", p: 1 }];
  }
  function generate(prompt, options = {}) {
    const maxNew = options.maxNew ?? 120;
    const temperature = options.temperature ?? 0.8;
    let out = String(prompt);
    for (let i = 0; i < maxNew; i++) {
      let dist = nextDist(out);
      dist = dist.map((d) => ({ ch: d.ch, p: Math.pow(d.p, 1 / Math.max(0.1, temperature)) }));
      let sum = dist.reduce((s, d) => s + d.p, 0);
      let r = Math.random() * sum;
      let ch = dist[0].ch;
      for (const d of dist) {
        r -= d.p;
        if (r <= 0) {
          ch = d.ch;
          break;
        }
      }
      out += ch;
      if (ch === "\n" && options.stopOnNewline) break;
    }
    return out.slice(prompt.length);
  }
  function snapshot() {
    return { order, contexts: counts.size, trained, type: "char-ngram" };
  }
  return { train, generate, nextDist, snapshot };
}
export default createCharNgram;
