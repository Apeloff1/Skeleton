"""Capability-replay balance and real native scoring interruption contracts."""
from __future__ import annotations

import time
import unittest
from collections import Counter
from unittest.mock import patch

from skeleton.ai.training.jeeves_capability_replay import (
    CapabilityReplayError, schedule_capability_replay,
)
from skeleton.cortex.transformer import TinyTransformer


def corpus(n=12):
    return tuple("Jeeves module jeeves."+domain+".specialty_"+str(i)+".lens. Objective: "
                 +"native task "+str(i)+" User: question Jeeves: verified example "+str(i)
                 for domain in ("gaming","ai","coding") for i in range(n))


class Scorer:
    def __init__(self,constant=False):
        self.constant=constant
        self.calls=[]
    def logprob(self,text):
        self.calls.append(text)
        if self.constant:
            return -1.0
        domain=next(x for x in ("gaming","ai","coding") if "jeeves."+x+"." in text)
        return {"gaming":-10000.0,"ai":-100.0,"coding":-1.0}[domain]


class CapabilityReplayBalanceTests(unittest.TestCase):
    def test_tied_losses_distinct_domain_rehearsal(self):
        rows=corpus(4)
        model=Scorer(constant=True)
        selected,receipt=schedule_capability_replay(model,rows,max_examples=6)
        self.assertEqual(len(set(selected)),6)
        self.assertEqual(receipt["selected_domains"],{"ai":2,"coding":2,"gaming":2})
        self.assertEqual(model.calls,list(rows))

    def test_raw_loss_scale_cannot_starve_lower_loss_domains(self):
        rows=corpus(16)
        selected,receipt=schedule_capability_replay(Scorer(),rows,max_examples=18)
        self.assertEqual(receipt["selected_domains"],{"ai":6,"coding":6,"gaming":6})
        self.assertEqual(len(set(selected)),18)
        self.assertEqual(receipt["active_specialties"],18)
        self.assertFalse(receipt["weights_modified_by_scheduler"])

    def test_training_order_and_reproducible_selection(self):
        rows=corpus(10)
        a,receipt=schedule_capability_replay(Scorer(),rows,max_examples=13)
        b,second=schedule_capability_replay(Scorer(),rows,max_examples=13)
        self.assertEqual(a,b)
        self.assertEqual(receipt["selected_example_sha256"],second["selected_example_sha256"])
        self.assertEqual(a,tuple(x for x in rows if x in set(a)))
        self.assertLessEqual(max(receipt["selected_domains"].values())-
                             min(receipt["selected_domains"].values()),1)

    def test_underrepresented_domain_does_not_invent_examples(self):
        rows=tuple(x for x in corpus(10)
                   if "jeeves.coding." not in x or "specialty_0." in x or "specialty_1." in x)
        selected,receipt=schedule_capability_replay(Scorer(),rows,max_examples=12)
        self.assertEqual(receipt["selected_domains"]["coding"],2)
        self.assertEqual(len(selected),12)

    def test_deadline_validated_and_expired_before_scoring(self):
        model=Scorer()
        for deadline in (True,float("nan"),float("inf"),time.monotonic()-10):
            with self.subTest(deadline=deadline),self.assertRaises(CapabilityReplayError):
                schedule_capability_replay(model,corpus(),deadline=deadline)
        self.assertFalse(model.calls)

    def test_third_party_scorer_checked_after_return(self):
        model=Scorer()
        with patch("skeleton.ai.training.jeeves_capability_replay.time.monotonic",
                   side_effect=[0.0,10.0]):
            with self.assertRaises(CapabilityReplayError):
                schedule_capability_replay(model,corpus(),deadline=5.0)
        self.assertEqual(len(model.calls),1)

    def test_native_model_polls_inside_sample(self):
        model=TinyTransformer(vocab=("native","task","question","verified","example"),
                              dim=8,ctx=64,seed=9)
        # The genuine native scorer receives a deadline callback; this
        # deterministic clock expires during its actual teacher-forced pass.
        with patch("skeleton.ai.training.jeeves_capability_replay.time.monotonic",
                   side_effect=[0.0,0.0,10.0]):
            with self.assertRaises(CapabilityReplayError):
                schedule_capability_replay(model,corpus(3),max_examples=6,deadline=5.0)

    def test_nonfinite_loss_never_admitted(self):
        model=Scorer()
        model.logprob=lambda _:float("-inf")
        with self.assertRaises(CapabilityReplayError):
            schedule_capability_replay(model,corpus())

    def test_unreviewed_format_or_duplicate_denied(self):
        rows=corpus(3)
        for changed in (rows+("raw unclassified document",),rows+(rows[0],)):
            with self.assertRaises(CapabilityReplayError):
                schedule_capability_replay(Scorer(),changed,max_examples=6)

if __name__=="__main__":
    unittest.main()
