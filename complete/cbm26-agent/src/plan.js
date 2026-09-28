export function createPlanner() {
  function plan(input, ctx = {}) {
    const text = String(input || "").trim();
    const lower = text.toLowerCase();
    if (!text) return { action: "respond", reason: "empty_input", say: "Send a message to begin." };
    if (/^(remember|note|save):/i.test(text) || lower.startsWith("remember "))
      return { action: "remember", reason: "user_asked_to_remember", content: text.replace(/^(remember|note|save):\s*/i, "") };
    if (/^(what did|recall|find|search)/i.test(text) || lower.includes("do you remember"))
      return { action: "retrieve", reason: "user_asked_to_recall", query: text };
    if (/^reflect|status|metrics/i.test(text)) return { action: "reflect", reason: "operator_status" };
    if ((ctx.storeCount || 0) > 0 && text.length > 12)
      return { action: "retrieve_then_respond", reason: "ground_response", query: text };
    return { action: "respond", reason: "direct", say: null };
  }
  return { plan };
}
