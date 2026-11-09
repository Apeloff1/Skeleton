import { createSystem } from "./conductor.js";
import { createCBM26 } from "./agent.js";
import { createIntegratedAI } from "./ai.js";
import { createControlHub } from "./control.js";
import { createIdleController } from "./idle.js";
import { createUI } from "./ui.js";

export async function createApp(options = {}) {
  const system = createSystem(options);
  await system.boot();
  const control = createControlHub();
  const idle = createIdleController(options.idle);
  const ui = createUI(options.ui);
  return {
    name: "jeeves",
    system,
    control,
    idle,
    ui,
    cycle: (s) => system.cycle(s),
    snapshot: () => ({
      system: system.snapshot(),
      control: control.snapshot(),
      idle: idle.snapshot(),
      ui: ui.snapshot(),
    }),
    factories: { createCBM26, createIntegratedAI, createSystem, createControlHub, createIdleController, createUI },
  };
}

export { createSystem } from "./conductor.js";
export { createCBM26 } from "./agent.js";
export { createIntegratedAI } from "./ai.js";
export { createControlHub } from "./control.js";
export { createIdleController } from "./idle.js";
export { createUI } from "./ui.js";
export default createApp;
