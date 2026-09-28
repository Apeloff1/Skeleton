/**
 * Slim MASTER Ω conductor for the complete tree.
 * Composes agent + integrated AI. No missing PROD imports.
 */
export function createSystem(options = {}) {
  const projectId = options.projectId || "MASTER_Ω";
  let agent = null;
  let cycles = 0;
  const log = [];

  async function boot() {
    const { createCBM26 } = await import("../../cbm26-agent/src/index.js");
    agent = createCBM26(options.agent || {});
    log.push({ at: Date.now(), event: "boot", projectId });
    return snapshot();
  }

  async function cycle(stimulus = "status") {
    if (!agent) await boot();
    cycles++;
    const out = await agent.turn(stimulus);
    const row = { at: Date.now(), cycle: cycles, action: out.decision?.action, ms: out.ms };
    log.push(row);
    if (log.length > 200) log.shift();
    return { ...out, cycle: cycles };
  }

  function snapshot() {
    return {
      projectId,
      cycles,
      agent: agent?.snapshot?.() || null,
      recent: log.slice(-8),
    };
  }

  return { boot, cycle, snapshot };
}
export default createSystem;
