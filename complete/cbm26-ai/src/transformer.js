import { zeros, randn, matmul, addBiasRow, gelu, layerNorm } from "./tensor.js";

export function createConfig(overrides = {}) {
  return { vocabSize: 260, dModel: 48, nHead: 4, nLayer: 2, dFF: 96, maxSeq: 40, ...overrides };
}

export function createModel(cfg) {
  const c = createConfig(cfg);
  const params = {
    tokEmb: randn([c.vocabSize, c.dModel], 0.02),
    posEmb: randn([c.maxSeq, c.dModel], 0.01),
    lmHead: randn([c.dModel, c.vocabSize], 0.02),
    lnF_g: zeros(c.dModel),
    lnF_b: zeros(c.dModel),
    layers: [],
  };
  for (let i = 0; i < c.dModel; i++) params.lnF_g.data[i] = 1;
  for (let L = 0; L < c.nLayer; L++) {
    const layer = {
      ln1_g: zeros(c.dModel), ln1_b: zeros(c.dModel),
      ln2_g: zeros(c.dModel), ln2_b: zeros(c.dModel),
      wQKV: randn([c.dModel, 3 * c.dModel], 0.02), bQKV: zeros(3 * c.dModel),
      wO: randn([c.dModel, c.dModel], 0.02), bO: zeros(c.dModel),
      w1: randn([c.dModel, c.dFF], 0.02), b1: zeros(c.dFF),
      w2: randn([c.dFF, c.dModel], 0.02), b2: zeros(c.dModel),
    };
    for (let i = 0; i < c.dModel; i++) { layer.ln1_g.data[i] = 1; layer.ln2_g.data[i] = 1; }
    params.layers.push(layer);
  }

  function forward(ids) {
    const T = Math.min(ids.length, c.maxSeq);
    const C = c.dModel;
    let X = zeros(T, C);
    for (let t = 0; t < T; t++) {
      const tok = Math.max(0, Math.min(c.vocabSize - 1, ids[t] | 0));
      for (let d = 0; d < C; d++) X.data[t * C + d] = params.tokEmb.data[tok * C + d] + params.posEmb.data[t * C + d];
    }
    for (const layer of params.layers) {
      const N = layerNorm(X, layer.ln1_g, layer.ln1_b);
      const qkv = addBiasRow(matmul(N, layer.wQKV), layer.bQKV);
      const attn = zeros(T, C);
      const scale = 1 / Math.sqrt(C);
      for (let t = 0; t < T; t++) {
        let max = -Infinity;
        const scores = new Float64Array(t + 1);
        for (let s = 0; s <= t; s++) {
          let dot = 0;
          for (let d = 0; d < C; d++) dot += qkv.data[t * 3 * C + d] * qkv.data[s * 3 * C + C + d];
          scores[s] = dot * scale;
          if (scores[s] > max) max = scores[s];
        }
        let sum = 0;
        for (let s = 0; s <= t; s++) { scores[s] = Math.exp(scores[s] - max); sum += scores[s]; }
        for (let d = 0; d < C; d++) {
          let acc = 0;
          for (let s = 0; s <= t; s++) acc += (scores[s] / sum) * qkv.data[s * 3 * C + 2 * C + d];
          attn.data[t * C + d] = acc;
        }
      }
      const O = addBiasRow(matmul(attn, layer.wO), layer.bO);
      for (let i = 0; i < X.data.length; i++) X.data[i] += O.data[i];
      const N2 = layerNorm(X, layer.ln2_g, layer.ln2_b);
      const H = gelu(addBiasRow(matmul(N2, layer.w1), layer.b1));
      const F = addBiasRow(matmul(H, layer.w2), layer.b2);
      for (let i = 0; i < X.data.length; i++) X.data[i] += F.data[i];
    }
    const hidden = layerNorm(X, params.lnF_g, params.lnF_b);
    const logits = matmul(hidden, params.lmHead);
    return { logits, T, hidden };
  }

  function paramCount() {
    let n = params.tokEmb.data.length + params.posEmb.data.length + params.lmHead.data.length;
    for (const L of params.layers) n += L.wQKV.data.length + L.wO.data.length + L.w1.data.length + L.w2.data.length;
    return n;
  }

  return { config: c, params, forward, paramCount };
}
export default { createConfig, createModel };
