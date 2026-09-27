import { createBaselineAI } from "./model.js";
import { createCharNgram } from "./char_lm.js";
import { readFile } from "fs/promises";

export async function createAmazingBaseline(options = {}) {
  const corpus =
    options.corpus ||
    (await readFile(new URL("../data/corpus.txt", import.meta.url), "utf8").catch(() =>
      "The residual measures distance from equilibrium.\nLower residual means coherent structure.\n"
    ));
  const neural = createBaselineAI({
    config: options.config || { dModel: 48, nHead: 4, nLayer: 2, dFF: 96, maxSeq: 40 },
    corpus,
  });
  const ngram = createCharNgram(options.order || 10);
  ngram.train(corpus.repeat(options.ngramRepeats || 5));
  let lastTrain = null;
  return {
    name: "CBM-26-AI-Amazing",
    train(text, opts) {
      const body = text || corpus;
      ngram.train(body.repeat(2));
      lastTrain = neural.train(body.repeat(2), opts || { epochs: 15, lr: 0.05 });
      return lastTrain;
    },
    generate(prompt, opts = {}) {
      if (opts.mode === "neural") return neural.generate(prompt, opts);
      const text = ngram.generate(prompt, {
        maxNew: opts.maxNew ?? 100,
        temperature: opts.temperature ?? 0.75,
      });
      return { text, prompt, engine: "char-ngram-10" };
    },
    lossOn(text) {
      return neural.lossOn(text);
    },
    snapshot() {
      return {
        name: "CBM-26-AI-Amazing",
        neural: neural.snapshot(),
        ngram: ngram.snapshot(),
        lastTrain: lastTrain
          ? { start: lastTrain.history[0]?.loss, end: lastTrain.history.at(-1)?.loss, epochs: lastTrain.history.length }
          : null,
      };
    },
    neural,
    ngram,
  };
}
export default createAmazingBaseline;
