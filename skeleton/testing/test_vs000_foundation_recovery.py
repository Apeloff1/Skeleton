from __future__ import annotations
from dataclasses import replace
from skeleton.persistence.foundation_recovery import *
def scenario():
 e1=DurableEvent(1,"EVENT.1",{"op":"set","key":"conversation","value":"ready"},None)
 e2=DurableEvent(2,"EVENT.2",{"op":"set","key":"counter","value":1},e1.digest)
 return VS000Scenario("SCENARIO.VS000",{"boot":True},(e1,e2))
def test_clean_bootstrap_checkpoint_restart_rebuild():
 s=scenario();cp=checkpoint(s,"CHECKPOINT.1");ev=recover(s,cp);assert ev.status is RecoveryStatus.RECOVERED;assert ev.rebuilt_projection_digest==cp.projection_digest
def test_event_chain_break_is_rejected_before_recovery():
 e1=DurableEvent(1,"EVENT.1",{"op":"set","key":"x","value":1},None);e2=DurableEvent(2,"EVENT.2",{"op":"set","key":"y","value":2},"0"*64)
 try:VS000Scenario("SCENARIO.X",{},(e1,e2));assert False
 except RecoveryError as exc:assert "chain mismatch" in str(exc)
def test_sequence_gap_is_rejected():
 e=DurableEvent(2,"EVENT.2",{"op":"set","key":"x","value":1},None)
 try:VS000Scenario("SCENARIO.X",{},(e,));assert False
 except RecoveryError as exc:assert "sequence gap" in str(exc)
def test_corrupted_checkpoint_event_digest_fails_closed():
 s=scenario();cp=replace(checkpoint(s,"CHECKPOINT.1"),event_digest="0"*64);assert recover(s,cp).status is RecoveryStatus.FAIL_CLOSED
def test_corrupted_projection_digest_fails_closed():
 s=scenario();cp=replace(checkpoint(s,"CHECKPOINT.1"),projection_digest="0"*64);assert recover(s,cp).status is RecoveryStatus.FAIL_CLOSED
def test_truncated_log_against_checkpoint_fails_closed():
 s=scenario();cp=checkpoint(s,"CHECKPOINT.1");truncated=VS000Scenario(s.scenario_id,s.initial_state,s.events[:1]);assert recover(truncated,cp).status is RecoveryStatus.FAIL_CLOSED
def test_replay_is_deterministic():
 s=scenario();assert project(s.initial_state,s.events)==project(s.initial_state,s.events)
def test_unsupported_event_never_becomes_authoritative_projection():
 e=DurableEvent(1,"EVENT.1",{"op":"execute","key":"x"},None);s=VS000Scenario("SCENARIO.X",{},(e,))
 try:checkpoint(s,"CHECKPOINT.X");assert False
 except RecoveryError as exc:assert "unsupported" in str(exc)
