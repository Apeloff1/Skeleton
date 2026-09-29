/** Command-plane UI stub. Sidebar on desktop, commands on mobile. */
export function createUI(options = {}) {
  const mode = options.mode || "desktop";
  function sidebar() {
    return {
      mode,
      panes: ["filetree", "workspace", "blackboard", "control"],
    };
  }
  function command(name) {
    return { ok: true, name: String(name || ""), mode };
  }
  return { sidebar, command, snapshot: () => ({ mode }) };
}
export default createUI;
