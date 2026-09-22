"""Memory distillation — decide what deserves memory before it costs tokens.

Wave-2 SOTA (2026 structured/adaptive agent-memory distillation work): the
win is not storing more — it is storing *less, losslessly for retrieval*.
This module sits between a raw episode stream and the memory tiers and
does three things:

1. **Worth gate** — an episode earns memory only if it carries signal:
   entity mentions, numbers, decisions, or unresolved questions. Filler
   ("ok", "thanks", pure acknowledgements) never reaches the store.
2. **Distill** — long episodes compress to a structured fact record
   (subject / gist / evidence pointers) rather than the raw transcript;
   the goal is retrieval preservation at a fraction of the tokens.
3. **Budget** — the distilled store enforces a token ceiling, evicting
   lowest-value entries first (value = importance × freshness).

Pure domain; deterministic; no embeddings required — the worth gate is a
lexical/structural heuristic so it runs in CI without a model.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from skeleton.memory.prefix_renderer import estimate_tokens

# ── Worth gate ───────────────────────────────────────────────────────────

_SIGNAL_NUMBER = re.compile(r"\d")
_SIGNAL_ENTITY = re.compile(r"\b[A-Z][a-z]{2,}\b")          # crude proper-noun cue
_SIGNAL_DECISION = re.compile(
    r"\b(decided|chose|will|must|never|always|agreed|because|therefore)\b", re.I
)
_SIGNAL_QUESTION = re.compile(r"\?")

# Non-lexical filler — entire-utterance matches that carry no signal.
# Extended 2026-08-30 from the original 12-word list: acknowledgements,
# affirmations, backchannels, and social openers/closers across English
# plus the common chat-register variants (no caps, abbreviations, emoji-
# adjacent forms). Matching is whole-utterance, case-insensitive, with
# optional trailing punctuation — substrings inside real content never
# match (e.g. "yes, the plan is…" still passes the gate).
NON_LEXICAL_WORDS = frozenset({
    # bare acknowledgements
    "ok", "okay", "k", "kk", "okok", "okey", "okei",
    "yes", "yeah", "yep", "yup", "ya", "aye", "yass", "yesss",
    "no", "nope", "nah", "nuh",
    "sure", "right", "correct", "true", "exactly", "indeed", "agreed",
    "fine", "good", "great", "nice", "cool", "awesome", "amazing",
    "perfect", "wonderful", "lovely", "brilliant", "fantastic",
    # gratitudes
    "thanks", "thank you", "thankyou", "thx", "ty", "tysm", "takk",
    "much appreciated", "appreciated", "cheers",
    # backchannels / continuers
    "got it", "gotcha", "i see", "understood", "understand", "noted",
    "makes sense", "fair enough", "fair", "mhm", "mm", "mmm", "uh huh",
    "uh-huh", "hmm", "hm", "aight", "alright", "all good",
    "sounds good", "looking good", "roger", "copy", "copy that", "ack",
    # social openers / closers (whole-utterance only)
    "hi", "hello", "hey", "yo", "sup", "hiya", "heyy",
    "bye", "goodbye", "cya", "see ya", "later", "gtg", "g2g", "ttyl",
    "good morning", "good evening", "good night", "gn",
    # hesitation / softeners
    "idk", "dunno", "maybe", "perhaps", "whatever", "meh",
    "lol", "lmao", "haha", "hahaha", "hehe",
    "oops", "whoops", "wow", "whoa", "oh", "ah", "huh", "eh",
})

_FILLER_PATTERN = re.compile(
    r"^(?:" + "|".join(re.escape(w) for w in sorted(NON_LEXICAL_WORDS, key=len, reverse=True)) + r")[.!…]*$",
    re.I,
)


def is_non_lexical(text: str) -> bool:
    """True iff the whole utterance is non-lexical filler."""
    return bool(_FILLER_PATTERN.match((text or "").strip()))


def worth_remembering(text: str, *, min_signal: int = 1) -> bool:
    """An episode earns memory iff it carries at least ``min_signal`` cues."""
    text = (text or "").strip()
    if not text or is_non_lexical(text):
        return False
    signal = 0
    if _SIGNAL_NUMBER.search(text):
        signal += 1
    if _SIGNAL_ENTITY.search(text):
        signal += 1
    if _SIGNAL_DECISION.search(text):
        signal += 1
    if _SIGNAL_QUESTION.search(text):
        signal += 1
    if len(text.split()) >= 12:  # substance threshold
        signal += 1
    return signal >= min_signal


# ── Distillation ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DistilledFact:
    """A compressed memory record. ``gist`` is the retrievable payload."""
    fact_id: str
    gist: str
    source_chars: int
    tokens: int
    entities: Tuple[str, ...]
    importance: float
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "gist": self.gist,
            "source_chars": self.source_chars,
            "tokens": self.tokens,
            "entities": list(self.entities),
            "importance": self.importance,
            "created_at": self.created_at,
        }


def distill(text: str, *, max_gist_words: int = 40,
            importance: float = 0.5) -> DistilledFact:
    """Compress an episode to its lead sentence(s) + entity anchors."""
    import hashlib
    raw = (text or "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", raw)
    gist_words: List[str] = []
    for sentence in sentences:
        for word in sentence.split():
            if len(gist_words) >= max_gist_words:
                break
            gist_words.append(word)
        if len(gist_words) >= max_gist_words:
            break
    gist = " ".join(gist_words)
    entities = tuple(sorted(set(_SIGNAL_ENTITY.findall(raw))))[:8]
    return DistilledFact(
        fact_id="fact_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        gist=gist,
        source_chars=len(raw),
        tokens=estimate_tokens(gist),
        entities=entities,
        importance=importance,
        created_at=time.time(),
    )


# ── Budgeted store ───────────────────────────────────────────────────────

class DistilledStore:
    """Token-capped store of distilled facts; evicts lowest value first."""

    def __init__(self, *, token_budget: int = 20_000) -> None:
        self.token_budget = token_budget
        self._facts: Dict[str, DistilledFact] = {}
        self._tokens_used = 0

    def _value(self, fact: DistilledFact, now: float) -> float:
        age_h = max(0.0, (now - fact.created_at) / 3600.0)
        return fact.importance / (1.0 + age_h / 24.0)  # halves daily

    def admit(self, text: str, *, importance: float = 0.5) -> Optional[DistilledFact]:
        """Gate → distill → budget-admit. Returns the fact, or None if gated out."""
        if not worth_remembering(text):
            return None
        fact = distill(text, importance=importance)
        while self._tokens_used + fact.tokens > self.token_budget and self._facts:
            now = time.time()
            victim_id = min(self._facts, key=lambda k: (self._value(self._facts[k], now), k))
            victim = self._facts.pop(victim_id)
            self._tokens_used -= victim.tokens
        if self._tokens_used + fact.tokens > self.token_budget:
            return None  # single fact larger than the whole budget
        self._facts[fact.fact_id] = fact
        self._tokens_used += fact.tokens
        return fact

    def search(self, query: str, *, top_k: int = 5) -> List[DistilledFact]:
        qwords = set(query.lower().split())
        scored = []
        for fact in self._facts.values():
            overlap = len(qwords & set(fact.gist.lower().split()))
            ent = len(qwords & {e.lower() for e in fact.entities})
            score = overlap + 2 * ent
            if score:
                scored.append((score, fact))
        scored.sort(key=lambda kv: (-kv[0], kv[1].fact_id))
        return [f for _, f in scored[:top_k]]

    def stats(self) -> Dict[str, Any]:
        return {
            "facts": len(self._facts),
            "tokens_used": self._tokens_used,
            "token_budget": self.token_budget,
            "utilisation": round(self._tokens_used / max(1, self.token_budget), 4),
        }
