"""Bounded relevance packing for an explicitly lossy local review context.

Retains complete original user/assistant pairs, in chronological order, with
source indices and digests. No summary model, synthesized instructions, or
durable transcript changes. Admission uses the caller's real context estimator.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
import re
import unicodedata

MAX_SCAN_TURNS = 96
MAX_SELECTED_TURNS = 24
MAX_ADMISSION_CHECKS = 40
MAX_PAIR_CHARS = 32768
_MAX_TERMS = 768
_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_STOP = frozenset("the of a an and or to in that is it for on with as at this by be from are was i you we me my your".split())


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _terms(value):
    normalized = unicodedata.normalize("NFKC", value[:MAX_PAIR_CHARS]).casefold()
    words = [m.group() for m in _WORDS.finditer(normalized)
             if m.group() not in _STOP and 1 < len(m.group()) <= 96][:_MAX_TERMS]
    # Exact CJK character bigrams improve retrieval on unsegmented text.
    for match in re.finditer(r"[\u3400-\u9fff\u3040-\u30ff]+", normalized):
        block = match.group()
        words.extend(block[i:i+2] for i in range(min(len(block)-1, 128)))
        if len(words) >= _MAX_TERMS:
            break
    return Counter(words[:_MAX_TERMS])


def _pairs(history):
    if type(history) is not tuple or len(history) % 2:
        raise ValueError("complete committed history pairs required")
    size = len(history)//2
    lower = max(0, size-MAX_SCAN_TURNS)
    result = []
    for index in range(lower, size):
        pair = history[index*2:index*2+2]
        if any(type(row) is not tuple or len(row) != 2 or
               type(row[1]) is not str or not row[1].strip() for row in pair):
            raise ValueError("invalid committed history pair")
        if pair[0][0] != "user" or pair[1][0] != "assistant":
            raise ValueError("invalid conversation role ordering")
        if sum(len(row[1]) for row in pair) <= MAX_PAIR_CHARS:
            result.append((index, pair))
    return size, lower, result


def pack_history(question, history, *, fits, recent_turns=2, max_turns=MAX_SELECTED_TURNS):
    """Greedy bounded relevance packing, with exact-or-conservative admission.

    Caller supplies a tokenizer-backed predicate on complete history tuples.
    No claim of global optimality or semantic entailment. Omitted older turns
    stay in the authoritative transcript and are explicitly counted.
    """
    if (type(question) is not str or not question.strip() or len(question) > 4096
            or not callable(fits) or type(recent_turns) is not int
            or not 0 <= recent_turns <= 4 or type(max_turns) is not int
            or not 1 <= max_turns <= MAX_SELECTED_TURNS):
        raise ValueError("invalid relevance context policy")
    total, lower, rows = _pairs(history)
    q = _terms(question)
    vocabulary = {}
    df = Counter()
    for index, pair in rows:
        # User intent has priority; assistant text is context, not authority.
        user, assistant = _terms(pair[0][1]), _terms(pair[1][1])
        vocabulary[index] = (user, assistant)
        df.update(set(user) | set(assistant))

    def rank(index):
        user, assistant = vocabulary[index]
        match = sum(math.log1p((len(rows)+1)/(1+df[t]))*
                    (2*min(3,user[t])+min(2,assistant[t])) for t in q)
        norm = math.sqrt(1+sum(user.values())+.5*sum(assistant.values()))
        return match/norm

    lookup = dict(rows)
    recent = [i for i, _ in reversed(rows) if i >= total-recent_turns]
    ranked = sorted((i for i, _ in rows if i not in recent),
                    key=lambda i: (-rank(i), -i))
    # No zero-overlap ancient turns selected merely to fill the window.
    ranked = [i for i in ranked if rank(i) > 0]
    selected = []
    checks = 1
    if fits(()) is not True:
        raise ValueError("base request does not fit context")
    for index in recent + ranked:
        if checks >= MAX_ADMISSION_CHECKS or len(selected) >= max_turns:
            break
        trial = sorted(selected+[index])
        candidate = tuple(row for i in trial for row in lookup[i])
        checks += 1
        decision = fits(candidate)
        if type(decision) is not bool:
            raise ValueError("context admission must return boolean")
        if decision:
            selected = trial
    chosen = tuple(row for i in selected for row in lookup[i])
    report = {
        "schema": "skeleton.jeeves.relevance-history.v1",
        "method": "bounded_lexical_pair_packing",
        "question_sha256": sha256(question.encode()).hexdigest(),
        "total_turns": total, "scan_start_turn": lower,
        "eligible_turns": len(rows), "selected_turns": [
            {"turn_index": i, "pair_sha256": digest(lookup[i]),
             "recency_priority": i >= total-recent_turns} for i in selected
        ],
        "omitted_turns": total-len(selected), "admission_checks": checks,
        "admission_check_cap": MAX_ADMISSION_CHECKS,
        "scan_truncated": lower > 0,
        "history_modified": False, "summarized": False,
        "semantic_relevance_verified": False,
        "selected_history_sha256": digest(chosen),
    }
    report["receipt_sha256"] = digest(report)
    return chosen, report
