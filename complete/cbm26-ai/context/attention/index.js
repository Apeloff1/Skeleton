export function createAttentionLattice(options = {}) {
  const cubes = options.cubes || 9;
  const faces = [];
  for (let i = 0; i < cubes; i++) faces.push({ id: "att_" + i, tokens: 0, stamp: Date.now() });
  function track(n) {
    const c = faces[Math.abs(n) % faces.length];
    c.tokens += Math.max(1, n | 0);
    c.stamp = Date.now();
    return c;
  }
  function snapshot() {
    return { cubes, faces: faces.map((f) => ({ ...f })) };
  }
  return { track, snapshot, faces };
}
export default createAttentionLattice;
