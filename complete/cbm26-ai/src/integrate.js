/**
 * Wire CBM-26-AI to the quad context stack.
 * Context is RAM + tiers. Model generates. Memory persists.
 */
export async function createIntegratedAI(options = {}) {
  const { createAmazingBaseline } = await import("./ensemble.js");
  let createContextArchitecture = null;
  let createContext2027 = null;
  try {
    ({ createContextArchitecture } = await import("../context/arch2026/index.js"));
  } catch {}
  try {
    ({ createContext2027 } = await import("../context/arch2027/index.js"));
  } catch {}

  const ai = await createAmazingBaseline(options);
  const ctx26 = typeof createContextArchitecture === "function" ? createContextArchitecture(options.ctx26 || {}) : null;
  const ctx27 = typeof createContext2027 === "function" ? createContext2027(options.ctx27 || {}) : null;

  return {
    name: "CBM-26-AI-Integrated",
    ai,
    ctx26,
    ctx27,
    async turn(text) {
      if (ctx26?.ingest) ctx26.ingest({ role: "user", text });
      if (ctx27?.ingest) ctx27.ingest(String(text));
      const out = ai.generate(String(text), options.gen || {});
      if (ctx26?.ingest) ctx26.ingest({ role: "assistant", text: out.text || out });
      return {
        text: out.text || out,
        engine: out.engine || "ensemble",
        context: {
          arch2026: ctx26?.snapshot?.() || null,
          arch2027: ctx27?.snapshot?.() || null,
        },
      };
    },
    snapshot() {
      return {
        ai: ai.snapshot(),
        arch2026: ctx26?.snapshot?.() || null,
        arch2027: ctx27?.snapshot?.() || null,
      };
    },
  };
}

export default createIntegratedAI;
