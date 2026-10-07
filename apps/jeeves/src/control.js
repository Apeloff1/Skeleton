/** Traffic / control hub face. Lights only. No route graph dump. */
export function createControlHub() {
  const lights = { boot: "green", agent: "green", ai: "yellow", backend: "green" };
  function set(plane, color) {
    if (!lights[plane]) lights[plane] = color;
    else lights[plane] = color;
    return snapshot();
  }
  function snapshot() {
    return { lights: { ...lights }, at: Date.now() };
  }
  return { set, snapshot, name: "control-hub" };
}
export default createControlHub;
