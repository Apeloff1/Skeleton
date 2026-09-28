export function createMemoryEval() {
  const probes = [];
  function probe(snap = {}) {
    const memoryTotal = snap.memorySnap?.total ?? snap.queryHits?.length ?? 0;
    const skillCount = snap.skillSnap?.count ?? 0;
    const budgetUtil = snap.budgetSnap?.utilization ?? 0;
    const score = Math.max(0, Math.min(1, 0.4 + Math.min(0.3, memoryTotal / 50) + Math.min(0.2, skillCount / 10) - budgetUtil * 0.1));
    const row = { at: Date.now(), score, memoryTotal, skillCount, budgetUtil };
    probes.push(row);
    if (probes.length > 100) probes.shift();
    return row;
  }
  function snapshot() {
    return { n: probes.length, last: probes[probes.length - 1] || null };
  }
  return { probe, snapshot };
}
export default createMemoryEval;
