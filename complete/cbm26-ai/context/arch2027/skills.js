export function createSkillRegistry() {
  const skills = new Map();
  const invocations = [];
  function register(name, body, meta = {}) {
    const skill = {
      name: String(name),
      body: typeof body === "function" ? null : String(body),
      fn: typeof body === "function" ? body : null,
      uses: 0,
      success: 0,
      tags: meta.tags || [],
    };
    skills.set(skill.name, skill);
    return skill;
  }
  function invoke(name, input = {}) {
    const skill = skills.get(String(name));
    if (!skill) return { ok: false, reason: "missing_skill", name };
    skill.uses++;
    let result = null;
    let ok = true;
    try {
      result = skill.fn ? skill.fn(input) : { echo: skill.body, input };
    } catch (e) {
      ok = false;
      result = { error: String(e.message || e) };
    }
    if (ok) skill.success++;
    invocations.push({ at: Date.now(), name, ok });
    return { ok, result, skill: { name: skill.name, uses: skill.uses } };
  }
  function fromProceduralText(text) {
    const m = String(text).match(/Skill:\s*(.+)/i);
    if (!m) return null;
    const name = m[1].slice(0, 80).trim() || "anon";
    return register(name, text, { tags: ["induced"] });
  }
  function snapshot() {
    return { count: skills.size, names: [...skills.keys()], invocations: invocations.length };
  }
  return { register, invoke, fromProceduralText, snapshot };
}
export default createSkillRegistry;
