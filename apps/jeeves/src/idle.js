/** Idle acquisition. Starts when the operator is not driving a cycle. */
export function createIdleController(options = {}) {
  let running = false;
  let ticks = 0;
  const periodMs = options.periodMs || 60000;
  function start(onTick) {
    running = true;
    return { running, periodMs, onTick: typeof onTick === "function" };
  }
  function stop() {
    running = false;
    return snapshot();
  }
  function tick() {
    if (!running) return { skipped: true, ticks };
    ticks++;
    return { ticks, running };
  }
  function snapshot() {
    return { running, ticks, periodMs };
  }
  return { start, stop, tick, snapshot };
}
export default createIdleController;
