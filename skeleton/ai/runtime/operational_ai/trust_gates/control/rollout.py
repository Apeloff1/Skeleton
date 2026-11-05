"""Operator-controlled model rollout with explicit evidence and bounded rollback."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from .model_epoch import ModelEpoch
from ..applications.release_evidence import qualify_record

class ModelRollout:
    def __init__(self,active:ModelEpoch,*,maximum_history=16):
        if type(maximum_history) is not int or not 1<=maximum_history<=128:
            fail("invalid rollout history ceiling")
        self.active=active;self._lock=RLock()
        self._history=[];self._staged=None;self._limit=maximum_history

    def stage(self,*,model_sha,tokenizer_sha,head_sha,observed,
              reviewed,real_e2e,rights,installation):
        with self._lock:
            if self._staged is not None: fail("rollout already staged")
            receipt=qualify_record(head_sha=head_sha,observed=observed,
                 reviewed=reviewed,native_e2e=real_e2e,rights_approved=rights,
                 installation_proved=installation)
            self._staged={"model_sha":model_sha,"tokenizer_sha":tokenizer_sha,
                          "evidence":receipt,"previous":self.active.identity}
            return dict(self._staged)

    def commit(self,*,approved=False):
        if approved is not True: fail("rollout needs separate operator approval")
        with self._lock:
            if self._staged is None: fail("no verified rollout staged")
            if len(self._history)>=self._limit: fail("bounded rollback history full")
            candidate=self._staged
            previous=self.active.identity
            if previous!=candidate["previous"]: fail("rollout base epoch changed")
            next_epoch=self.active.swap(candidate["model_sha"],candidate["tokenizer_sha"],
                                        expected=previous,approved=True)
            self._history.append(previous)
            self._staged=None
            return next_epoch

    def abort(self):
        with self._lock:
            if self._staged is None: fail("no staged rollout")
            self._staged=None

    def rollback(self,*,approved=False):
        if approved is not True: fail("rollback requires operator approval")
        with self._lock:
            if not self._history: fail("no previously approved epoch")
            previous=self._history[-1]
            old=self.active.identity
            new=self.active.swap(previous[1],previous[2],expected=old,approved=True)
            self._history.pop()
            self._staged=None
            return new
