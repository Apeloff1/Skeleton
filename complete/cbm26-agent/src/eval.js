export function createEval() {
  const runs = [];
  function record(row) {
    runs.push({ at: Date.now(), ...row });
    if (runs.length > 200) runs.shift();
    return row;
  }
  function summary() {
    const n = runs.length || 1;
    const ms = runs.map((r) => r.ms || 0);
    const mean = ms.reduce((a, b) => a + b, 0) / n;
    return { n: runs.length, meanMs: mean, last: runs[runs.length - 1] || null };
  }
  return { record, summary };
}
