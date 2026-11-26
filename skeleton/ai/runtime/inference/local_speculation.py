"""Request-local n-gram speculation with conservative acceptance feedback.

This is a token-ID proposal kernel for a future native target verifier.
No second model, cross-request cache, network, or unverified token output.
The owner must use its existing native target verification before committing
ANY draft tokens. This module alone cannot accelerate llama.cpp CLI.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
from itertools import islice
import json


def _int(x, lo, hi):
    if type(x) is not int or not lo <= x <= hi:
        raise ValueError("bounded integer required")


def _pin(s):
    if type(s) is not str or len(s)!=64 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError("SHA256 required")


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class Scope:
    principal_sha256: str
    request_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    runtime_sha256: str
    policy_sha256: str

    def __post_init__(self):
        for x in (self.principal_sha256,self.request_sha256,self.model_sha256,
                  self.tokenizer_sha256,self.runtime_sha256,self.policy_sha256):
            _pin(x)

    @property
    def identity(self):
        return _digest([self.principal_sha256,self.request_sha256,self.model_sha256,
                        self.tokenizer_sha256,self.runtime_sha256,self.policy_sha256])


@dataclass(frozen=True, slots=True)
class Policy:
    vocab_size: int
    history_tokens: int=8192
    ngram: int=6
    max_draft: int=16
    min_hits: int=2
    min_agreement_bp: int=8000
    max_rounds: int=4096
    max_output_tokens: int=8192
    cooldown_rounds: int=8

    def __post_init__(self):
        for value,lo,hi in ((self.vocab_size,1,1<<24),(self.history_tokens,32,65536),
                            (self.ngram,2,24),(self.max_draft,1,64),
                            (self.min_hits,1,32),(self.min_agreement_bp,5001,10000),
                            (self.max_rounds,1,65536),(self.max_output_tokens,1,8192),(self.cooldown_rounds,1,128)):
            _int(value,lo,hi)
        if self.history_tokens < self.ngram+self.max_draft:
            raise ValueError("insufficient history capacity")

    @property
    def identity(self):
        return _digest([getattr(self,k) for k in self.__dataclass_fields__])


@dataclass(frozen=True, slots=True)
class Draft:
    scope_sha256: str
    prefix_sha256: str
    round_id: int
    token_ids: tuple[int,...]
    remaining_output: int

    @property
    def identity(self):
        return _digest([self.scope_sha256,self.prefix_sha256,self.round_id,self.token_ids,self.remaining_output])


@dataclass(frozen=True, slots=True)
class Feedback:
    scope_sha256: str
    draft_sha256: str
    target_receipt_sha256: str
    accepted_prefix: int
    baseline_elapsed_us: int
    verified_elapsed_us: int

    def __post_init__(self):
        for v in (self.scope_sha256,self.draft_sha256,self.target_receipt_sha256):
            _pin(v)
        _int(self.accepted_prefix,0,64)
        _int(self.baseline_elapsed_us,1,86_400_000_000)
        _int(self.verified_elapsed_us,1,86_400_000_000)


class LocalDraftWindow:
    """Bounded single-request state; no token persistence or shared pool."""

    def __init__(self,scope:Scope,policy:Policy,*,prompt_tokens):
        if type(scope) is not Scope or type(policy) is not Policy or scope.policy_sha256!=policy.identity:
            raise ValueError("request-local speculation identity mismatch")
        self.scope=scope
        self.policy=policy
        self._history=deque(maxlen=policy.history_tokens)
        # Prompt may exceed the reusable tail; retain only last bounded window.
        # Enforce global input ceiling rather than consume an endless iterable.
        self._prefix_hash=sha256(b"jeeves-speculation-prefix-v1")
        self._length=0
        self._pending=None
        self._round=0
        self._draft_limit=policy.max_draft
        self._cooldown=0
        self._good=0
        self._bad=0
        self._closed=False
        self._index=defaultdict(Counter)
        for token in islice(prompt_tokens,1_048_577):
            if self._length>=1_048_576:
                self.close()
                raise ValueError("prompt token stream exceeds finite ceiling")
            self._append(token)
        self._prompt_length=self._length

    def _append(self,token):
        _int(token,0,self.policy.vocab_size-1)
        n=self.policy.ngram
        if len(self._history)==self.policy.history_tokens:
            oldest=tuple(islice(self._history,n+1))
            key=oldest[:n]
            counter=self._index[key]
            counter[oldest[n]]-=1
            if not counter[oldest[n]]:
                del counter[oldest[n]]
            if not counter:
                del self._index[key]
        if len(self._history)>=n:
            # deque slicing is avoided; only last n entries are visited.
            suffix=tuple(reversed(tuple(islice(reversed(self._history),n))))
            self._index[suffix][token]+=1
        self._history.append(token)
        self._prefix_hash.update(token.to_bytes(4,"big"))
        self._length+=1

    @property
    def prefix_sha256(self):
        return self._prefix_hash.hexdigest()

    def propose(self,*,remaining_output:int) -> Draft|None:
        if self._closed or self._pending is not None:
            raise ValueError("closed or already pending speculation round")
        _int(remaining_output,0,8192)
        if remaining_output > self.policy.max_output_tokens-(self._length-self._prompt_length):
            raise ValueError("proposal exceeds original generation ceiling")
        if not remaining_output or self._round>=self.policy.max_rounds:
            return None
        self._round+=1
        if self._cooldown:
            self._cooldown-=1
            return None
        n=self.policy.ngram
        key=tuple(reversed(tuple(islice(reversed(self._history),n))))
        if len(key)!=n:
            return None
        draft=[]
        for _ in range(min(remaining_output,self._draft_limit)):
            counts=self._index.get(key)
            if not counts:
                break
            # Deterministic winner; do not sample or claim target probability.
            token,hits=min(counts.items(),key=lambda pair:(-pair[1],pair[0]))
            if hits<self.policy.min_hits or hits*10000<sum(counts.values())*self.policy.min_agreement_bp:
                break
            draft.append(token)
            key=key[1:]+(token,)
        if not draft:
            return None
        result=Draft(self.scope.identity,self.prefix_sha256,self._round,tuple(draft),remaining_output)
        self._pending=result
        return result

    def observe(self,feedback:Feedback,*,committed_target_tokens:tuple[int,...]):
        """Only owner-observed target tokens extend the history.

        The receipt digest is caller supplied and has to be independently
        verified before this call. A hash string is not an attestation.
        No draft is published by this method. Exact greedy equivalence
        requires target backend verification under the original sampler.
        """
        if self._closed or self._pending is None or type(feedback) is not Feedback:
            raise ValueError("no pending target verification")
        draft=self._pending
        if feedback.scope_sha256!=self.scope.identity or feedback.draft_sha256!=draft.identity:
            raise ValueError("different target feedback scope")
        if type(committed_target_tokens) is not tuple or not 1<=len(committed_target_tokens)<=min(len(draft.token_ids)+1,draft.remaining_output):
            raise ValueError("invalid committed target sequence")
        for x in committed_target_tokens:
            _int(x,0,self.policy.vocab_size-1)
        matched=0
        for a,b in zip(draft.token_ids,committed_target_tokens):
            if a!=b:
                break
            matched+=1
        if matched!=feedback.accepted_prefix or matched>len(draft.token_ids):
            raise ValueError("inconsistent accepted prefix")
        # On rejection the target must supply its own replacement, not accept
        # a shorter draft as output. Full acceptance permits a bonus token.
        if matched<len(draft.token_ids) and len(committed_target_tokens)!=matched+1:
            raise ValueError("rejected draft lacks target replacement")
        if self._length-self._prompt_length+len(committed_target_tokens)>self.policy.max_output_tokens:
            raise ValueError("request history ceiling exceeded")
        for x in committed_target_tokens:
            self._append(x)
        self._pending=None
        profitable=(matched*10000>=len(draft.token_ids)*self.policy.min_agreement_bp
                    and feedback.verified_elapsed_us<feedback.baseline_elapsed_us)
        if profitable:
            self._good+=1
            self._bad=0
            if self._good>=3:
                self._draft_limit=min(self.policy.max_draft,self._draft_limit+1)
                self._good=0
        else:
            self._good=0
            self._bad+=1
            self._draft_limit=max(1,self._draft_limit//2)
            if self._bad>=3:
                self._cooldown=self.policy.cooldown_rounds
                self._bad=0

    def append_target(self,tokens:tuple[int,...]):
        """Observe ordinary verified generation when no proposal is pending."""
        if self._closed or self._pending is not None or type(tokens) is not tuple or not 1<=len(tokens)<=8192:
            raise ValueError("invalid ordinary target token update")
        if self._length-self._prompt_length+len(tokens)>self.policy.max_output_tokens:
            raise ValueError("request history ceiling exceeded")
        for x in tokens:
            _int(x,0,self.policy.vocab_size-1)
        for x in tokens:
            self._append(x)

    def close(self):
        self._closed=True
        self._history.clear()
        self._index.clear()
        self._pending=None
        self._prefix_hash=sha256(b"jeeves-speculation-closed-v1")

    def stats(self):
        return {"scope_sha256":self.scope.identity,"rounds":self._round,
                "bounded_history_tokens":len(self._history),
                "indexed_ngrams":len(self._index),"draft_limit":self._draft_limit,
                "cooldown":self._cooldown,"closed":self._closed}
