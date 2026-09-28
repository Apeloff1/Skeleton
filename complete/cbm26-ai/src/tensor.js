export function zeros(...shape) {
  const n = shape.reduce((a, b) => a * b, 1);
  return { data: new Float64Array(n), shape };
}
export function randn(shape, scale = 0.02) {
  const t = zeros(...shape);
  for (let i = 0; i < t.data.length; i++) {
    const u = 1 - Math.random();
    const v = Math.random();
    t.data[i] = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) * scale;
  }
  return t;
}
export function matmul(A, B) {
  const [m, k] = A.shape;
  const n = B.shape[1];
  const C = zeros(m, n);
  for (let i = 0; i < m; i++) {
    for (let p = 0; p < k; p++) {
      const a = A.data[i * k + p];
      for (let j = 0; j < n; j++) C.data[i * n + j] += a * B.data[p * n + j];
    }
  }
  return C;
}
export function addBiasRow(X, b) {
  const [T, C] = X.shape;
  const Y = zeros(T, C);
  for (let t = 0; t < T; t++) for (let c = 0; c < C; c++) Y.data[t * C + c] = X.data[t * C + c] + b.data[c];
  return Y;
}
export function gelu(X) {
  const Y = zeros(...X.shape);
  for (let i = 0; i < X.data.length; i++) {
    const x = X.data[i];
    Y.data[i] = 0.5 * x * (1 + Math.tanh(Math.sqrt(2 / Math.PI) * (x + 0.044715 * x * x * x)));
  }
  return Y;
}
export function layerNorm(X, g, b) {
  const [T, C] = X.shape;
  const Y = zeros(T, C);
  for (let t = 0; t < T; t++) {
    let mean = 0;
    for (let c = 0; c < C; c++) mean += X.data[t * C + c];
    mean /= C;
    let var_ = 0;
    for (let c = 0; c < C; c++) {
      const d = X.data[t * C + c] - mean;
      var_ += d * d;
    }
    var_ = Math.sqrt(var_ / C + 1e-5);
    for (let c = 0; c < C; c++) Y.data[t * C + c] = ((X.data[t * C + c] - mean) / var_) * g.data[c] + b.data[c];
  }
  return Y;
}
export default { zeros, randn, matmul, addBiasRow, gelu, layerNorm };
