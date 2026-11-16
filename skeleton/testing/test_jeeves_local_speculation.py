"""Scoped speculative draft tests; no native decoding performance claim."""
import unittest
from dataclasses import replace
from hashlib import sha256
from skeleton.ai.runtime.inference.local_speculation import (
    Scope, Policy, LocalDraftWindow, Feedback,
)


def pin(s):
    return sha256(s.encode()).hexdigest()


def window(**kwargs):
    p=Policy(32,ngram=2,max_draft=4,**kwargs)
    scope=Scope(*(pin(x) for x in ("principal","request","model","tokenizer","runtime")),p.identity)
    return LocalDraftWindow(scope,p,prompt_tokens=(1,2,3,4)*4+(1,2))


def feedback(w,d,n,fast=True):
    return Feedback(w.scope.identity,d.identity,pin("target"),n,1000,500 if fast else 1500)


class LocalSpeculationTests(unittest.TestCase):
    def test_repeat_draft_and_exact_prefix(self):
        w=window()
        d=w.propose(remaining_output=4)
        self.assertEqual(d.token_ids,(3,4,1,2))
        old=w.prefix_sha256
        w.observe(feedback(w,d,4),committed_target_tokens=d.token_ids)
        self.assertNotEqual(w.prefix_sha256,old)

    def test_rejected_draft_needs_target_replacement(self):
        w=window()
        d=w.propose(remaining_output=4)
        with self.assertRaises(ValueError):
            w.observe(feedback(w,d,1),committed_target_tokens=(3,))
        w.observe(feedback(w,d,1),committed_target_tokens=(3,7))
        self.assertEqual(w.stats()["draft_limit"],2)

    def test_cross_request_and_inconsistent_acceptance_hold(self):
        w=window()
        d=w.propose(remaining_output=4)
        for f in (replace(feedback(w,d,4),scope_sha256=pin("other")),
                  feedback(w,d,3)):
            with self.assertRaises(ValueError):
                w.observe(f,committed_target_tokens=d.token_ids)

    def test_original_output_ceiling_and_bonus_token(self):
        w=window(max_output_tokens=4)
        d=w.propose(remaining_output=4)
        with self.assertRaises(ValueError):
            w.observe(feedback(w,d,4),committed_target_tokens=d.token_ids+(3,))
        w.observe(feedback(w,d,4),committed_target_tokens=d.token_ids)
        with self.assertRaises(ValueError):
            w.append_target((3,))

    def test_history_never_exceeds_limit(self):
        w=window(history_tokens=32)
        w.append_target((1,2,3,4)*100)
        self.assertLessEqual(w.stats()["bounded_history_tokens"],32)
        self.assertLessEqual(w.stats()["indexed_ngrams"],32)
        self.assertEqual(w.propose(remaining_output=4).token_ids,(1,2,3,4))

    def test_close_clears_request_state(self):
        w=window()
        w.propose(remaining_output=4)
        w.close()
        self.assertEqual(w.stats()["bounded_history_tokens"],0)
        self.assertEqual(w.stats()["indexed_ngrams"],0)
        with self.assertRaises(ValueError):
            w.propose(remaining_output=4)

    def test_no_cross_request_index(self):
        w=window()
        other=replace(w.scope,request_sha256=pin("different"))
        fresh=LocalDraftWindow(other,w.policy,prompt_tokens=(1,2))
        self.assertIsNone(fresh.propose(remaining_output=4))

    def test_conflicting_next_tokens_abstain(self):
        p=Policy(32,ngram=2,max_draft=4)
        sc=replace(window().scope,policy_sha256=p.identity)
        w=LocalDraftWindow(sc,p,prompt_tokens=(1,2,3,1,2,4,1,2,3,1,2,4,1,2))
        self.assertIsNone(w.propose(remaining_output=4))

    def test_slow_verification_reduces_draft(self):
        w=window()
        d=w.propose(remaining_output=4)
        w.observe(feedback(w,d,4,False),committed_target_tokens=d.token_ids)
        self.assertEqual(w.stats()["draft_limit"],2)

    def test_pending_round_blocks_ordinary_append(self):
        w=window()
        w.propose(remaining_output=4)
        with self.assertRaises(ValueError):
            w.append_target((3,))


if __name__=="__main__":
    unittest.main()
