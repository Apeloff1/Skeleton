"""GameForge BPE — a tokenizer the model owns, not a regex.

Word-level `tokens()` stays the Jaccard/fingerprint spine. This encoder
is the other mouth: character pairs merge on the closed-world corpus
until frequent spells (`ttk`, `dps`, `soul`) are single symbols and
unseen concatenations still split. Compression ratio < 1 is the proof
it is a model of the dialect, not a split() wrapper. Snapshot/restore
is interchange — hive B speaks the same pieces.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence, Tuple

PAD = " "
UNK = "�"


def _chars(text: str) -> Tuple[str, ...]:
    return tuple((text or "").lower()) or (PAD,)


def _pairs(stream: Sequence[str]) -> Counter:
    c: Counter = Counter()
    for i in range(len(stream) - 1):
        c[(stream[i], stream[i + 1])] += 1
    return c


def _apply(stream: Sequence[str], pair: Tuple[str, str], merged: str) -> List[str]:
    out: List[str] = []
    i = 0
    a, b = pair
    n = len(stream)
    while i < n:
        if i + 1 < n and stream[i] == a and stream[i + 1] == b:
            out.append(merged)
            i += 2
        else:
            out.append(stream[i])
            i += 1
    return out


def _encode_indexed(stream: Sequence[str], merges: Sequence[Tuple[str, str, str]]) -> Tuple[str, ...]:
    """Ordered BPE with a mutable occurrence index, exact legacy semantics.

    The legacy encoder scans every surviving character for every merge.
    Index only edges whose pair appears in the rules. A rule consumes a
    snapshot of its matching original edges, in original left-to-right
    order. Adjacent updates touch at most three edges. Newly formed edges
    cannot participate in the current wave, even for unusual restored
    rules with repeated pairs or an output equal to an input.
    """
    n = len(stream)
    if n <= 1:
        return tuple(stream)
    wanted = {(a, b) for a, b, _ in merges}
    # If the initial stream cannot match any rule then no merge can occur.
    symbols = list(stream)
    following = list(range(1, n)) + [-1]
    previous = [-1] + list(range(n - 1))
    versions = [0] * n
    postings: Dict[Tuple[str, str], set[int]] = {}

    def remove(left: int) -> None:
        if left < 0:
            return
        right = following[left]
        if right < 0:
            return
        pair = (symbols[left], symbols[right])
        positions = postings.get(pair)
        if positions is not None:
            positions.discard(left)
            if not positions:
                del postings[pair]

    def insert(left: int) -> None:
        if left < 0:
            return
        right = following[left]
        if right < 0:
            return
        pair = (symbols[left], symbols[right])
        if pair in wanted:
            postings.setdefault(pair, set()).add(left)

    for i in range(n - 1):
        insert(i)
    for a, b, merged in merges:
        positions = postings.get((a, b))
        if not positions:
            if not postings:
                break
            continue
        # Snapshot endpoints and versions. Newly inserted adjacencies,
        # including a previously indexed left endpoint, are not matches
        # from the start of this merge wave.
        wave = [(i, following[i], versions[i], versions[following[i]])
                for i in sorted(positions)]
        for left, right, lv, rv in wave:
            if (following[left] != right or following[right] == -2
                    or versions[left] != lv or versions[right] != rv):
                continue
            before, after = previous[left], following[right]
            remove(before)
            remove(left)
            remove(right)
            symbols[left] = merged
            versions[left] += 1
            versions[right] += 1
            following[left] = after
            following[right] = -2  # removed node
            previous[right] = -2
            if after >= 0:
                previous[after] = left
            insert(before)
            insert(left)
    result: List[str] = []
    i = 0
    while i >= 0:
        result.append(symbols[i])
        i = following[i]
    return tuple(result)


class BytePairEncoder:
    """Character BPE. Fit on GameForge text. Encode/decode is the contract."""

    def __init__(self, *, merges: int = 96) -> None:
        self.merges_n = max(8, int(merges))
        self.merges: List[Tuple[str, str, str]] = []
        self.itos: List[str] = []
        self.stoi: Dict[str, int] = {}
        self.fitted = 0
        self.base_chars: List[str] = []

    def fit(self, texts: Iterable[str]) -> int:
        corpus = [_chars(t) for t in texts if t]
        if not corpus:
            corpus = [_chars("hp dps ttk mix trash elite boss")]
        alphabet = sorted({ch for s in corpus for ch in s})
        self.base_chars = list(alphabet)
        vocab = set(alphabet)
        streams = [list(s) for s in corpus]
        self.merges = []
        for _ in range(self.merges_n):
            freq: Counter = Counter()
            for s in streams:
                freq.update(_pairs(s))
            if not freq:
                break
            pair, n = freq.most_common(1)[0]
            if n < 2:
                break
            merged = pair[0] + pair[1]
            if merged in vocab:
                # collision with an existing symbol — skip by tagging
                merged = merged + "·"
            vocab.add(merged)
            self.merges.append((pair[0], pair[1], merged))
            streams = [_apply(s, pair, merged) for s in streams]
        self.itos = [UNK] + sorted(vocab)
        self.stoi = {t: i for i, t in enumerate(self.itos)}
        self.fitted = sum(len(s) for s in corpus)
        return len(self.merges)

    def encode_pieces(self, text: str) -> Tuple[str, ...]:
        stream = _chars(text)
        # Build an occurrence index only when the avoided scans justify
        # its linear scratch. Very large prompts retain the bounded
        # legacy memory profile; the optimized backend stays exact.
        if 256 <= len(stream) <= 131072 and len(self.merges) >= 16:
            return _encode_indexed(stream, self.merges)
        current = list(stream)
        for a, b, m in self.merges:
            current = _apply(current, (a, b), m)
        return tuple(current)

    def encode_ids(self, text: str) -> List[int]:
        return [int(self.stoi.get(p, 0)) for p in self.encode_pieces(text)]

    def decode(self, pieces: Sequence[str]) -> str:
        return "".join(str(p).replace("·", "") for p in pieces)

    def compression(self, text: str) -> float:
        chars = max(1, len(_chars(text)))
        return len(self.encode_pieces(text)) / chars

    def covers(self, piece: str) -> bool:
        return piece in self.stoi

    def snapshot(self) -> Dict[str, Any]:
        return {
            "merges_n": self.merges_n,
            "merges": [list(m) for m in self.merges],
            "itos": list(self.itos),
            "fitted": self.fitted,
            "base_chars": list(self.base_chars),
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "BytePairEncoder":
        bpe = cls(merges=int((data or {}).get("merges_n") or 96))
        bpe.merges = [tuple(m) for m in ((data or {}).get("merges") or [])]  # type: ignore[misc]
        itos = list((data or {}).get("itos") or [UNK])
        bpe.itos = itos
        bpe.stoi = {t: i for i, t in enumerate(itos)}
        bpe.fitted = int((data or {}).get("fitted") or 0)
        bpe.base_chars = list((data or {}).get("base_chars") or [])
        return bpe

    def to_dict(self) -> Dict[str, Any]:
        return {
            "merges": len(self.merges),
            "vocab": len(self.itos),
            "fitted": self.fitted,
        }


def gameforge_bpe(*, merges: int = 96) -> BytePairEncoder:
    from skeleton.cortex.lm import gameforge_corpus
    enc = BytePairEncoder(merges=merges)
    enc.fit(gameforge_corpus())
    return enc
