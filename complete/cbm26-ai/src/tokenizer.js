export function createCharTokenizer(corpus = "") {
  const chars = [...new Set(String(corpus))].sort();
  if (!chars.includes("\n")) chars.push("\n");
  if (!chars.includes(" ")) chars.push(" ");
  const stoi = new Map();
  const itos = new Map();
  let i = 3;
  for (const ch of chars) {
    if (!stoi.has(ch)) {
      stoi.set(ch, i);
      itos.set(i, ch);
      i++;
    }
  }
  const vocabSize = i;
  const BOS = 1, EOS = 2, PAD = 0;
  function encode(text, addSpecial = true) {
    const ids = [];
    if (addSpecial) ids.push(BOS);
    for (const ch of String(text)) ids.push(stoi.has(ch) ? stoi.get(ch) : PAD);
    if (addSpecial) ids.push(EOS);
    return ids;
  }
  function decode(ids) {
    let s = "";
    for (const id of ids) {
      if (id === BOS || id === EOS || id === PAD) continue;
      s += itos.get(id) ?? "";
    }
    return s;
  }
  return { encode, decode, vocabSize, BOS, EOS, PAD, stoi, itos, chars };
}
export function createByteTokenizer() {
  return createCharTokenizer("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,;:!?-'\n");
}
export default createCharTokenizer;
