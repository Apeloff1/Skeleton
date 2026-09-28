export function sampleLogits(logitRow, V, options = {}) {
  const temperature = options.temperature ?? 0.9;
  const topK = options.topK ?? 40;
  const scores = [];
  for (let v = 0; v < V; v++) scores.push({ v, s: logitRow[v] / Math.max(1e-6, temperature) });
  scores.sort((a, b) => b.s - a.s);
  const top = scores.slice(0, Math.min(topK, scores.length));
  let max = top[0].s;
  let sum = 0;
  const probs = top.map((t) => {
    const e = Math.exp(t.s - max);
    sum += e;
    return e;
  });
  let r = Math.random() * sum;
  for (let i = 0; i < top.length; i++) {
    r -= probs[i];
    if (r <= 0) return top[i].v;
  }
  return top[0].v;
}
export function generate(model, tokenizer, prompt, options = {}) {
  const maxNew = options.maxNew ?? 80;
  let ids = tokenizer.encode(prompt, true);
  if (ids[ids.length - 1] === tokenizer.EOS) ids = ids.slice(0, -1);
  const outIds = [];
  for (let i = 0; i < maxNew; i++) {
    const ctx = ids.slice(-model.config.maxSeq);
    const { logits, T } = model.forward(ctx);
    const last = (T - 1) * model.config.vocabSize;
    const row = [];
    for (let v = 0; v < model.config.vocabSize; v++) row.push(logits.data[last + v]);
    const next = sampleLogits(row, model.config.vocabSize, options);
    if (next === tokenizer.EOS) break;
    ids.push(next);
    outIds.push(next);
  }
  return { text: tokenizer.decode(outIds), ids: outIds, prompt };
}
export default { generate, sampleLogits };
