export function createSegmentConsolidator(options = {}) {
  const maxChars = options.maxChars || 4000;
  let current = { id: "seg_1", text: "", at: Date.now() };
  let seq = 1;
  const finalized = [];

  function observe(text, meta = {}) {
    const chunk = String(text || "");
    current.text += (current.text ? "\n" : "") + chunk;
    let done = null;
    if (current.text.length >= maxChars || meta.finalize) {
      done = { ...current, finalizedAt: Date.now() };
      finalized.push(done);
      seq++;
      current = { id: "seg_" + seq, text: "", at: Date.now() };
    }
    return { finalized: done, current };
  }

  function snapshot() {
    return { currentId: current.id, finalized: finalized.length, currentChars: current.text.length };
  }

  return { observe, snapshot, finalizeCurrent: () => observe("", { finalize: true }) };
}

export default createSegmentConsolidator;
