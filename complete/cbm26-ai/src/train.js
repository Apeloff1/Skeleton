export function crossEntropyLoss(logits, targets) {
  const [T, V] = logits.shape;
  let loss = 0, count = 0;
  for (let t = 0; t < T - 1; t++) {
    const y = targets[t + 1];
    if (y == null || y < 0 || y >= V) continue;
    let max = -Infinity;
    for (let v = 0; v < V; v++) max = Math.max(max, logits.data[t * V + v]);
    let sum = 0;
    for (let v = 0; v < V; v++) sum += Math.exp(logits.data[t * V + v] - max);
    loss -= logits.data[t * V + y] - max - Math.log(sum);
    count++;
  }
  return count ? loss / count : 0;
}

export function trainStep(model, ids, lr = 0.05) {
  const { logits, T, hidden } = model.forward(ids);
  const loss = crossEntropyLoss(logits, ids);
  const V = model.config.vocabSize;
  const C = model.config.dModel;
  const lm = model.params.lmHead;
  for (let t = 0; t < T - 1; t++) {
    const y = ids[t + 1];
    if (y == null || y < 0 || y >= V) continue;
    let max = -Infinity;
    for (let v = 0; v < V; v++) max = Math.max(max, logits.data[t * V + v]);
    let sum = 0;
    const p = new Float64Array(V);
    for (let v = 0; v < V; v++) { p[v] = Math.exp(logits.data[t * V + v] - max); sum += p[v]; }
    for (let v = 0; v < V; v++) {
      const g = p[v] / (sum || 1) - (v === y ? 1 : 0);
      if (Math.abs(g) < 1e-10) continue;
      for (let d = 0; d < C; d++) {
        const clip = Math.max(-1, Math.min(1, hidden.data[t * C + d] * g));
        lm.data[d * V + v] -= lr * clip;
      }
    }
  }
  return loss;
}

export function trainOnText(model, tokenizer, text, opts = {}) {
  const epochs = opts.epochs ?? 8;
  const lr = opts.lr ?? 0.05;
  const ids = tokenizer.encode(String(text), true);
  const history = [];
  const window = model.config.maxSeq;
  for (let e = 0; e < epochs; e++) {
    let acc = 0, n = 0;
    for (let i = 0; i < ids.length - 2; i += Math.max(1, Math.floor(window / 2))) {
      const slice = ids.slice(i, i + window);
      if (slice.length < 4) continue;
      acc += trainStep(model, slice, lr);
      n++;
    }
    history.push({ epoch: e + 1, loss: n ? acc / n : 0 });
  }
  return { history };
}
export default { trainOnText, trainStep, crossEntropyLoss };
