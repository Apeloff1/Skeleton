"""Lock-protected model epoch and active-operation pinning."""
from __future__ import annotations
from contextlib import contextmanager
from threading import RLock
from ..contracts import fail

class ModelEpoch:
    def __init__(self, model_sha, tokenizer_sha):
        self._lock=RLock()
        self._generation=1
        self._active=0
        self._closed=False
        self._identity=(model_sha,tokenizer_sha)
        self._validate_identity(model_sha,tokenizer_sha)

    @staticmethod
    def _validate_identity(model_sha,tokenizer_sha):
        import re
        for entry in (model_sha,tokenizer_sha):
            if type(entry) is not str or re.fullmatch("[0-9a-f]{64}",entry) is None:
                fail("invalid pinned model/tokenizer SHA")

    @property
    def identity(self):
        with self._lock: return (self._generation,*self._identity)

    @contextmanager
    def pin(self, expected=None):
        with self._lock:
            if self._closed: fail("model slot closed")
            if expected is not None and expected!=(self._generation,*self._identity):
                fail("model identity stale")
            self._active+=1
            current=(self._generation,*self._identity)
        try:
            yield current
        finally:
            with self._lock:
                self._active-=1
                if self._active<0: fail("model pin corrupted")

    def swap(self,model_sha,tokenizer_sha,*,expected=None,approved=False):
        self._validate_identity(model_sha,tokenizer_sha)
        with self._lock:
            if not approved: fail("unapproved model swap")
            if self._closed or self._active: fail("model busy or closed")
            if expected is not None and expected!=(self._generation,*self._identity):
                fail("model compare-and-set conflict")
            if (model_sha,tokenizer_sha)==self._identity:
                fail("same model cannot create an artificial epoch")
            self._generation+=1
            self._identity=(model_sha,tokenizer_sha)
            return (self._generation,*self._identity)

    def close(self):
        with self._lock:
            if self._active: fail("cannot retire pinned model")
            self._closed=True
