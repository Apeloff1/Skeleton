import { createSystem } from "./conductor.js";
import { createCBM26 } from "./agent.js";
import { createIntegratedAI } from "./ai.js";

export async function createApp(options = {}) {
  const system = createSystem(options);
  await system.boot();
  return {
    name: "jeeves",
    system,
    cycle: (s) => system.cycle(s),
    snapshot: () => system.snapshot(),
    factories: { createCBM26, createIntegratedAI, createSystem },
  };
}

export { createSystem } from "./conductor.js";
export { createCBM26 } from "./agent.js";
export { createIntegratedAI } from "./ai.js";
export default createApp;
