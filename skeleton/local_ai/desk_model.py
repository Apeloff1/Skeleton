"""Local desk model: BM25 memory, a linear intent model, and short programs.

This is not a GGUF runtime. It does not load weights from a provider and it
does not call one. Priors live in this file. Anything it learns is a clipped
token weight stored beside the desk.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_MAX_FILE_BYTES = 64 * 1024
_MAX_EXAMPLE_CHARS = 240
_LEARNING_RATE = 0.5
_WEIGHT_CLIP = 4.0
_EPOCHS = 8
_SCORE_GATE = 1.0
_PHRASE_BONUS = 0.5
_K1 = 1.2
_B = 0.75
_SECRET = re.compile(r"(?i)\b(api[_-]?key|secret|password|token|bearer)\b\s*[:=]")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CHAIN = re.compile(r"\s+and then\s+", re.IGNORECASE)
_QUOTED = re.compile(r'"([^"]*)"')
_EXCLUSION = re.compile(r"(?<!\S)-([^\W_]+)", re.UNICODE)
_DOC_TAIL = re.compile(
    r"(?i)\s+(?:in|into|as|to)\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:pdf|docx|word|deck|slides?|pptx|xlsx|spreadsheet|workbook|document)\s*$"
)
_DOC_HEAD = re.compile(
    r"(?i)^(?:please\s+)?(?:make|write|create|export|put|place)\s+"
    r"(?:a\s+|an\s+|the\s+)?(?:pdf|docx|word|deck|slides?|pptx|xlsx|spreadsheet|"
    r"workbook|document)\s+(?:of|with|for|about)?\s*"
)
_FEATURE = re.compile(r"tok:[^\W_]{1,40}\Z", re.UNICODE)

NO_EVIDENCE = "No evidence in the local desk model."

CLASSES = (
    "remember",
    "forget",
    "replace",
    "ask",
    "reason",
    "pdf",
    "docx",
    "deck",
    "xlsx",
    "media",
    "append",
    "recall",
    "hash",
)
DIRECT = frozenset(CLASSES)
PRONOUNS = frozenset({"that", "it", "this", "the last note"})
ANSWER_PRONOUNS = frozenset({"the last answer"})

_STOP = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "of", "to", "in", "on",
        "for", "and", "or", "with", "be", "as", "at", "by", "from", "into",
        "it", "this", "that", "please",
    }
)
_WH = frozenset({"who", "what", "when", "where", "why", "how", "which"})
_CUES = {
    "remember_cue": frozenset({"save", "remember", "note", "store", "keep", "record"}),
    "forget_cue": frozenset({"forget", "drop", "erase", "remove"}),
    "replace_cue": frozenset({"replace", "change", "swap"}),
    "ask_cue": frozenset({"ask", "find", "lookup"}),
    "reason_cue": frozenset({"explain", "reason", "because", "summarize", "summarise"}),
    "append_cue": frozenset({"append", "add", "continue"}),
    "recall_cue": frozenset({"recall", "earlier"}),
    "hash_cue": frozenset({"hash", "checksum", "sha"}),
    "pdf": frozenset({"pdf"}),
    "docx": frozenset({"docx", "word"}),
    "deck": frozenset({"deck", "slide", "slides", "pptx"}),
    "xlsx": frozenset({"xlsx", "spreadsheet", "workbook", "sheet"}),
    "media": frozenset({"media", "audio", "video", "probe", "inspect", "plan", "trim", "convert"}),
}
_PRIORS: dict[str, dict[str, float]] = {
    "remember": {"bias": 0.15, "remember_cue": 2.6, "pronoun": -0.2},
    "forget": {"bias": -0.45, "forget_cue": 2.8},
    "replace": {"bias": -0.5, "replace_cue": 2.8, "pipe": 1.5},
    "ask": {"bias": -0.25, "ask_cue": 2.5, "question": 0.5, "wh": 0.35},
    "reason": {"bias": -0.35, "reason_cue": 2.5, "question": 1.15, "wh": 1.7},
    "pdf": {"bias": -0.55, "pdf": 3.0},
    "docx": {"bias": -0.55, "docx": 3.0},
    "deck": {"bias": -0.55, "deck": 3.0},
    "xlsx": {"bias": -0.55, "xlsx": 3.0},
    "media": {"bias": -0.6, "media": 2.8},
    "append": {"bias": -0.65, "append_cue": 2.9, "pdf": 0.7, "docx": 0.7, "deck": 0.7, "xlsx": 0.7},
    "recall": {"bias": -0.7, "recall_cue": 2.9},
    "hash": {"bias": -0.7, "hash_cue": 2.9},
}
_PREFIX = {
    "remember": _CUES["remember_cue"] | {"please"},
    "forget": _CUES["forget_cue"] | {"please"},
    "replace": _CUES["replace_cue"] | {"please"},
    "ask": _CUES["ask_cue"] | {"please"},
    "reason": _CUES["reason_cue"] | _WH | {"please"},
}


class ModelRejected(ValueError):
    """A local-model update or program was refused."""


@dataclass(frozen=True)
class ScoredFact:
    index: int
    text: str
    score: float
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class ModelAnswer:
    text: str
    confidence: float
    covered: bool
    evidence: tuple[ScoredFact, ...]


@dataclass(frozen=True)
class Prediction:
    label: str
    score: float
    confidence: float
    features: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    verb: str
    payload: str
    score: float
    resolve: str


@dataclass(frozen=True)
class Program:
    steps: tuple[Step, ...]
    confident: bool
    reason: str


class DeskModel:
    """BM25 over desk notes plus a perceptron that only learns token weights."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        max_features: int = 48,
        max_examples: int = 32,
    ) -> None:
        if isinstance(max_features, bool) or not isinstance(max_features, int) or not 1 <= max_features <= 256:
            raise ModelRejected("feature cap is invalid")
        if isinstance(max_examples, bool) or not isinstance(max_examples, int) or not 1 <= max_examples <= 32:
            raise ModelRejected("example cap is invalid")
        self.path = Path(path)
        if self.path.is_symlink():
            raise ModelRejected("model path is a symlink")
        self._max_features = max_features
        self._max_examples = max_examples
        self._learned: dict[str, dict[str, float]] = {}
        self._examples: list[tuple[str, str]] = []
        self._updates = 0
        self._last_text = ""
        self._load()

    @property
    def bound(self) -> bool:
        return True

    @property
    def remote(self) -> bool:
        return False

    @property
    def examples(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._examples)

    def status(self) -> dict[str, object]:
        learned = sorted({feature for table in self._learned.values() for feature in table})
        return {
            "bound": True,
            "remote": False,
            "gguf": False,
            "weights_source": "desk-corpus",
            "updates": self._updates,
            "examples": len(self._examples),
            "learned_features": learned,
            "classes": list(CLASSES),
        }

    def score_facts(self, query: str, facts: list[str]) -> list[ScoredFact]:
        """Rank facts with BM25 plus a bonus when query terms sit side by side."""
        phrases, terms, excluded = _query_parts(query)
        docs = [_words(fact) for fact in facts]
        eligible: list[int] = []
        for index, tokens in enumerate(docs):
            token_set = set(tokens)
            if any(term in token_set for term in excluded):
                continue
            if any(not _contains_phrase(tokens, phrase) for phrase in phrases):
                continue
            eligible.append(index)
        if not eligible:
            return []
        n = len(facts)
        avgdl = sum(len(tokens) for tokens in docs) / n if n else 0.0
        if avgdl <= 0:
            avgdl = 1e-9
        df = {term: sum(1 for tokens in docs if term in tokens) for term in terms}
        ranked: list[ScoredFact] = []
        for index in eligible:
            tokens = docs[index]
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            score = 0.0
            dl = len(tokens) or 1
            for term in terms:
                tf = counts.get(term, 0)
                if tf <= 0 or df.get(term, 0) <= 0:
                    continue
                idf = math.log(1.0 + (n - df[term] + 0.5) / (df[term] + 0.5))
                denom = tf + _K1 * (1.0 - _B + _B * dl / avgdl)
                score += idf * (tf * (_K1 + 1.0)) / denom
            score += _bigram_bonus(terms, tokens)
            ranked.append(ScoredFact(index + 1, facts[index], score, tuple(tokens)))
        ranked.sort(key=lambda item: (-item.score, item.index))
        return ranked

    def answer(self, query: str, facts: list[str]) -> ModelAnswer:
        if not isinstance(query, str) or not query.strip():
            raise ModelRejected("missing question")
        if not isinstance(facts, list) or any(not isinstance(fact, str) for fact in facts):
            raise ModelRejected("facts must be a list of strings")
        _phrases, terms, _excluded = _query_parts(query)
        ranked = [hit for hit in self.score_facts(query, facts) if hit.score > 0 or not terms]
        needed = set(terms)
        chosen: list[ScoredFact] = []
        covered: set[str] = set()
        for hit in ranked:
            if len(chosen) >= 3:
                break
            if hit.score <= 0:
                continue
            overlap = set(hit.tokens) & needed
            if needed and not overlap and chosen:
                continue
            chosen.append(hit)
            covered |= overlap
            if needed and covered == needed:
                break
        if not chosen or (needed and covered != needed):
            return ModelAnswer(NO_EVIDENCE, 0.0, False, ())
        lines = [f"{hit.text} [fact {hit.index} score {hit.score:.2f}]" for hit in chosen]
        confidence = chosen[0].score / (chosen[0].score + 1.0)
        return ModelAnswer("\n".join(lines), confidence, True, tuple(chosen))

    def classify(self, text: str) -> Prediction:
        features = self._features(text)
        best_label = CLASSES[0]
        best_score = self._logit(best_label, features)
        scores = {best_label: best_score}
        for label in CLASSES[1:]:
            score = self._logit(label, features)
            scores[label] = score
            if score > best_score:
                best_label = label
                best_score = score
        peak = max(scores.values())
        lifted = [math.exp(score - peak) for score in scores.values()]
        confidence = math.exp(best_score - peak) / sum(lifted)
        self._last_text = text.strip()
        ordered = tuple(sorted(features))
        return Prediction(best_label, best_score, confidence, ordered)

    def plan(self, utterance: str) -> Program:
        if not isinstance(utterance, str) or not utterance.strip():
            return Program((), False, "missing utterance")
        clauses = _clauses(utterance)
        if not clauses:
            return Program((), False, "missing utterance")
        if any(not clause for clause in clauses):
            return Program((), False, "empty clause")
        if len(clauses) > 4:
            return Program((), False, "too many clauses")
        steps: list[Step] = []
        for clause in clauses:
            verb, payload = _split_verb(clause)
            if verb in DIRECT:
                if not payload:
                    return Program((), False, "missing payload")
                steps.append(Step(verb, payload, _SCORE_GATE, _resolve_kind(verb, payload)))
                continue
            prediction = self.classify(clause)
            if prediction.score < _SCORE_GATE:
                return Program((), False, f"low confidence for '{clause}'")
            extracted = _extract(prediction.label, clause)
            if not extracted:
                return Program((), False, "missing payload")
            steps.append(
                Step(prediction.label, extracted, prediction.score, _resolve_kind(prediction.label, extracted))
            )
        return Program(tuple(steps), True, "ok")

    def teach(self, text: str, label: str) -> None:
        cleaned, label = self._validated_example(text, label)
        prospective = [(item, item_label) for item, item_label in self._examples if item.casefold() != cleaned.casefold()]
        prospective.append((cleaned, label))
        if len(prospective) > self._max_examples:
            prospective = prospective[-self._max_examples :]
        features = _feature_set(prospective)
        if len(features) > self._max_features:
            raise ModelRejected("too many learned features")
        self._examples = prospective
        self._retrain()
        self._updates += 1
        self._last_text = cleaned
        self.save()

    def judge(self, good: bool, label: str | None = None) -> str:
        if not isinstance(good, bool):
            raise ModelRejected("judge needs a boolean")
        if not self._last_text:
            raise ModelRejected("nothing to judge")
        if good:
            target = self.classify(self._last_text).label
        else:
            if not isinstance(label, str) or label.strip().casefold() not in DIRECT:
                raise ModelRejected("judge bad needs a label")
            target = label.strip().casefold()
        self.teach(self._last_text, target)
        return target

    def save(self) -> None:
        payload = {
            "version": 1,
            "updates": self._updates,
            "weights": {label: dict(sorted(table.items())) for label, table in sorted(self._learned.items()) if table},
            "examples": [{"text": text, "label": label} for text, label in self._examples],
            "last_text": self._last_text,
        }
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > _MAX_FILE_BYTES:
            raise ModelRejected("model file exceeds 64 KiB")
        _atomic_write(self.path, raw, prefix=".desk-model.")

    def _load(self) -> None:
        if not self.path.exists():
            self.save()
            return
        if self.path.is_symlink() or not self.path.is_file():
            raise ModelRejected("model file is not valid")
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ModelRejected("model file is not valid") from exc
        if len(raw.encode("utf-8")) > _MAX_FILE_BYTES:
            raise ModelRejected("model file exceeds 64 KiB")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ModelRejected("model file is not valid") from exc
        self._examples = _validated_store(payload, self._max_examples, self._max_features)
        self._retrain()
        if _learned_payload(self._learned) != payload["weights"]:
            raise ModelRejected("model file is not valid")
        self._updates = payload["updates"]
        self._last_text = payload["last_text"]

    def _retrain(self) -> None:
        self._learned = {}
        for _epoch in range(_EPOCHS):
            moved = False
            for text, label in self._examples:
                if self._update_once(text, label):
                    moved = True
            if not moved:
                break

    def _update_once(self, text: str, label: str) -> bool:
        prediction = self.classify(text)
        if prediction.label == label and prediction.score >= _SCORE_GATE:
            return False
        tokens = _content_tokens(text)
        if not tokens:
            return False
        for token in tokens:
            feature = f"tok:{token}"
            _bump(self._learned, label, feature, _LEARNING_RATE)
            if prediction.label != label:
                _bump(self._learned, prediction.label, feature, -_LEARNING_RATE)
        return True

    def _validated_example(self, text: object, label: object) -> tuple[str, str]:
        if not isinstance(text, str):
            raise ModelRejected("example must be a string")
        cleaned = text.strip()
        if not cleaned:
            raise ModelRejected("example is empty")
        if len(cleaned) > _MAX_EXAMPLE_CHARS:
            raise ModelRejected("example exceeds 240 characters")
        if any(ord(char) < 32 and char != "\t" for char in cleaned):
            raise ModelRejected("example contains a control character")
        if _SECRET.search(cleaned):
            raise ModelRejected("example contains a secret")
        if not isinstance(label, str) or label.strip().casefold() not in DIRECT:
            raise ModelRejected("unknown label")
        return cleaned, label.strip().casefold()

    def _features(self, text: str) -> set[str]:
        if not isinstance(text, str):
            raise ModelRejected("text must be a string")
        tokens = _words(text)
        features = {"bias"}
        if "?" in text:
            features.add("question")
        if "|" in text:
            features.add("pipe")
        if tokens and tokens[0] in _WH:
            features.add("wh")
        if any(token in {"that", "it", "this"} for token in tokens):
            features.add("pronoun")
        token_set = set(tokens)
        for name, words in _CUES.items():
            if token_set & words:
                features.add(name)
        known = {feature[4:] for table in self._learned.values() for feature in table}
        for token in _content_tokens(text):
            if token in known:
                features.add(f"tok:{token}")
        return features

    def _logit(self, label: str, features: set[str]) -> float:
        total = 0.0
        priors = _PRIORS[label]
        learned = self._learned.get(label, {})
        for feature in features:
            total += priors.get(feature, 0.0)
            total += learned.get(feature, 0.0)
        return total


def _words(text: str) -> list[str]:
    return [match.casefold() for match in _WORD.findall(text)]


def _content_tokens(text: str) -> list[str]:
    chosen: list[str] = []
    for token in _words(text):
        if token in _STOP or token in _WH:
            continue
        if len(token) > 40 or token in chosen:
            continue
        chosen.append(token)
        if len(chosen) == 8:
            break
    return chosen


def _feature_set(examples: list[tuple[str, str]]) -> set[str]:
    found: set[str] = set()
    for text, _label in examples:
        found.update(_content_tokens(text))
    return found


def _query_parts(query: str) -> tuple[list[str], list[str], list[str]]:
    if not isinstance(query, str):
        raise ModelRejected("missing question")
    phrases = [part.strip() for part in _QUOTED.findall(query) if part.strip()]
    stripped = _QUOTED.sub(" ", query)
    excluded = [match.group(1).casefold() for match in _EXCLUSION.finditer(stripped)]
    cleaned = _EXCLUSION.sub(" ", stripped)
    terms = [token for token in _words(cleaned) if token not in _STOP and token not in _WH]
    for phrase in phrases:
        terms.extend(token for token in _words(phrase) if token not in _STOP and token not in _WH)
    return phrases, _unique(terms), _unique(excluded)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _contains_phrase(tokens: list[str], phrase: str) -> bool:
    words = _words(phrase)
    if not words:
        return False
    if len(words) == 1:
        return words[0] in tokens
    window = len(words)
    return any(tokens[index : index + window] == words for index in range(len(tokens) - window + 1))


def _bigram_bonus(terms: list[str], tokens: list[str]) -> float:
    if len(terms) < 2:
        return 0.0
    pairs = set(zip(tokens, tokens[1:]))
    bonus = 0.0
    seen: set[tuple[str, str]] = set()
    for pair in zip(terms, terms[1:]):
        if pair in seen:
            continue
        seen.add(pair)
        if pair in pairs:
            bonus += _PHRASE_BONUS
    return bonus


def _clauses(text: str) -> list[str]:
    masked: list[str] = []
    in_quote = False
    for char in text:
        if char == '"':
            in_quote = not in_quote
            masked.append(char)
        elif in_quote and not char.isspace():
            masked.append("x")
        else:
            masked.append(char)
    parts: list[str] = []
    start = 0
    for match in _CHAIN.finditer("".join(masked)):
        parts.append(text[start : match.start()].strip())
        start = match.end()
    parts.append(text[start:].strip())
    return parts


def _split_verb(text: str) -> tuple[str, str]:
    verb, separator, payload = text.strip().partition(" ")
    if not separator:
        return verb.casefold(), ""
    return verb.casefold(), payload.strip()


def _resolve_kind(verb: str, payload: str) -> str:
    key = " ".join(payload.casefold().split())
    if key in PRONOUNS:
        return "fact"
    if key in ANSWER_PRONOUNS:
        return "answer"
    if verb != "append":
        return ""
    _head, _, rest = key.partition(" ")
    if rest in PRONOUNS:
        return "fact"
    if rest in ANSWER_PRONOUNS:
        return "answer"
    return ""


def _extract(label: str, clause: str) -> str:
    if label in {"pdf", "docx", "deck", "xlsx"}:
        quoted = [part.strip() for part in _QUOTED.findall(clause) if part.strip()]
        if quoted:
            return " | ".join(quoted)
        cleaned = _DOC_TAIL.sub("", clause).strip()
        cleaned = _DOC_HEAD.sub("", cleaned).strip()
        cleaned = re.sub(r"(?i)^(?:please\s+)?(?:put|place|make|write|create|export)\s+", "", cleaned).strip()
        return _payload_or_pronoun(clause, cleaned)
    if label == "append":
        match = re.search(
            r"(?i)\b(pdf|page|docx|paragraph|deck|slide|xlsx|row)\b\s+(.+)$",
            clause,
        )
        if match is None:
            return ""
        return f"{match.group(1).casefold()} {match.group(2).strip()}"
    if label == "hash":
        tokens = clause.split()
        if not tokens:
            return ""
        candidate = tokens[-1]
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", candidate) and ".." not in Path(candidate).parts:
            return candidate
        return ""
    if label == "recall":
        if re.search(r"(?i)\blast\b", clause):
            return "last"
        if re.search(r"(?i)\bcheck\b", clause):
            return "check"
        match = re.search(r"\b(\d+)\b", clause)
        return match.group(1) if match else ""
    if label == "media":
        match = re.search(r"(?i)\b(probe|inspect|plan|trim|convert)\b(.*)$", clause)
        if match is None:
            return ""
        rest = match.group(2).strip()
        return f"{match.group(1).casefold()} {rest}".strip()
    if label == "replace":
        payload = _strip_prefix(clause, _PREFIX["replace"])
        return payload if "|" in payload else ""
    if label in _PREFIX:
        return _payload_or_pronoun(clause, _strip_prefix(clause, _PREFIX[label]))
    return clause.strip()


def _strip_prefix(text: str, cues: frozenset[str] | set[str]) -> str:
    tokens = text.split()
    while tokens and tokens[0].casefold().strip("?:.,") in cues:
        tokens.pop(0)
        if tokens and tokens[0].casefold() in {"a", "an", "that"}:
            tokens.pop(0)
    return " ".join(tokens).strip()


def _payload_or_pronoun(original: str, payload: str) -> str:
    if payload:
        return payload
    for token in original.split():
        folded = token.casefold().strip("?:.,")
        if folded in {"that", "it", "this"}:
            return folded
    return ""


def _bump(learned: dict[str, dict[str, float]], label: str, feature: str, delta: float) -> None:
    table = learned.setdefault(label, {})
    value = max(-_WEIGHT_CLIP, min(_WEIGHT_CLIP, table.get(feature, 0.0) + delta))
    if value == 0.0:
        table.pop(feature, None)
        if not table:
            learned.pop(label, None)
        return
    table[feature] = value


def _learned_payload(learned: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {label: dict(sorted(table.items())) for label, table in sorted(learned.items()) if table}


def _validated_store(payload: object, max_examples: int, max_features: int) -> list[tuple[str, str]]:
    if not isinstance(payload, dict):
        raise ModelRejected("model file is not valid")
    allowed = {"version", "updates", "weights", "examples", "last_text"}
    if set(payload) != allowed or payload.get("version") != 1:
        raise ModelRejected("model file is not valid")
    updates = payload["updates"]
    if isinstance(updates, bool) or not isinstance(updates, int) or not 0 <= updates <= 1_000_000:
        raise ModelRejected("model file is not valid")
    if not isinstance(payload["last_text"], str) or len(payload["last_text"]) > _MAX_EXAMPLE_CHARS:
        raise ModelRejected("model file is not valid")
    weights = payload["weights"]
    examples = payload["examples"]
    if not isinstance(weights, dict) or not isinstance(examples, list) or len(examples) > max_examples:
        raise ModelRejected("model file is not valid")
    seen: set[str] = set()
    for label, table in weights.items():
        if label not in DIRECT or not isinstance(table, dict):
            raise ModelRejected("model file is not valid")
        for feature, value in table.items():
            if not isinstance(feature, str) or _FEATURE.fullmatch(feature) is None:
                raise ModelRejected("model file is not valid")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ModelRejected("model file is not valid")
            if not -_WEIGHT_CLIP <= float(value) <= _WEIGHT_CLIP:
                raise ModelRejected("model file is not valid")
            seen.add(feature[4:])
    if len(seen) > max_features:
        raise ModelRejected("model file is not valid")
    stored: list[tuple[str, str]] = []
    for item in examples:
        if not isinstance(item, dict) or set(item) != {"text", "label"}:
            raise ModelRejected("model file is not valid")
        text = item["text"]
        label = item["label"]
        if not isinstance(text, str) or not isinstance(label, str):
            raise ModelRejected("model file is not valid")
        if not text.strip() or len(text) > _MAX_EXAMPLE_CHARS or label not in DIRECT:
            raise ModelRejected("model file is not valid")
        if any(ord(char) < 32 and char != "\t" for char in text) or _SECRET.search(text):
            raise ModelRejected("model file is not valid")
        stored.append((text, label))
    return stored


def _atomic_write(path: Path, payload: bytes, *, prefix: str) -> None:
    parent = path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=parent)
    except OSError as exc:
        raise ModelRejected("model file could not be saved") from exc
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise ModelRejected("model file could not be saved") from exc
