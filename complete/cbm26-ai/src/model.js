import { createCharTokenizer, createByteTokenizer } from "./tokenizer.js";
import { createModel, createConfig } from "./transformer.js";
import { trainOnText, crossEntropyLoss } from "./train.js";
import { generate } from "./generate.js";

export function createBaselineAI(options = {}) {
  let tokenizer = options.corpus ? createCharTokenizer(options.corpus) : createByteTokenizer();
  const cfg = createConfig({ ...(options.config || {}), vocabSize: tokenizer.vocabSize });
  let model = createModel(cfg);
  function reinitFromCorpus(corpus) {
    tokenizer = createCharTokenizer(corpus);
    model = createModel(createConfig({ ...(options.config || {}), vocabSize: tokenizer.vocabSize }));
    return tokenizer.vocabSize;
  }
  return {
    name: "CBM-26-AI",
    get config() { return model.config; },
    get paramCount() { return model.paramCount(); },
    reinitFromCorpus,
    train(text, opts) {
      if (opts?.fitTokenizer !== false) reinitFromCorpus(text);
      return trainOnText(model, tokenizer, text, opts);
    },
    lossOn(text) {
      const ids = tokenizer.encode(text, true).slice(0, model.config.maxSeq);
      const { logits } = model.forward(ids);
      return crossEntropyLoss(logits, ids);
    },
    generate(prompt, opts) {
      return generate(model, tokenizer, prompt, opts);
    },
    snapshot() {
      return { name: "CBM-26-AI", config: model.config, parameters: model.paramCount(), vocabSize: tokenizer.vocabSize };
    },
    get _model() { return model; },
    get _tokenizer() { return tokenizer; },
  };
}
export default createBaselineAI;
