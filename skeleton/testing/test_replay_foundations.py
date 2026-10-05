from skeleton.ai.runtime.deferred.replay_foundations import *
def test_bulkhead_overflow_requires_capacity_and_authority():
 s=Bulkhead("a","critical",BulkheadLimit(1,1),1); t=Bulkhead("b","other",BulkheadLimit(1,1),0)
 assert not overflow(s,t,authority_compatible=False).admitted
 assert overflow(s,t,authority_compatible=True).target_bulkhead=="b"
def test_dead_letter_replay_requires_current_authorization_compatibility_idempotency():
 d=DeadLetter("op","d",3,"timeout","k")
 assert dead_letter_disposition(d,ReplayAuthorization("op",True,True,True)) is DeadLetterDisposition.REPLAY
 assert dead_letter_disposition(d,ReplayAuthorization("op",True,False,True)) is DeadLetterDisposition.HOLD
def test_reconstruction_and_simulation_have_no_external_effects():
 for m in (ReplayMode.RECONSTRUCT,ReplayMode.SIMULATE): assert not replay(ReplayRequest("op",m)).external_effects
def test_real_effect_replay_requires_reconciliation_and_idempotency():
 assert not replay(ReplayRequest("op",ReplayMode.REAL_EFFECT,True,False)).allowed
 assert replay(ReplayRequest("op",ReplayMode.REAL_EFFECT,True,True)).external_effects
def test_determinism_classes_use_declared_equivalence():
 assert DeterminismEnvelope(DeterminismClass.EXACT,None,VariancePolicy(0,0),()).equivalent(1,1)
 assert DeterminismEnvelope(DeterminismClass.TOLERANT,1,VariancePolicy(.1,0),()).equivalent(1,1.05)
 assert not DeterminismEnvelope(DeterminismClass.NONDETERMINISTIC,None,VariancePolicy(0,0),("scheduler",)).equivalent(1,1)
def test_deadline_uses_monotonic_duration_not_wall_clock():
 d=Deadline(100,Duration(10)); assert not d.expired(109) and d.expired(110)
def test_identifier_rejects_ambiguous_forms():
 for x in (" Operation:x","operation:X ","operation:x:y"):
  try: IdentifierCodec.parse(x); assert False
  except (ValueError,KeyError): pass
 assert IdentifierCodec.render(IdentifierCodec.parse("operation:x"))=="operation:x"
def test_sequence_does_not_infer_causality_across_domains():
 assert compare_sequence(SequenceNumber("a",1),SequenceNumber("b",2)) is CausalRelation.UNKNOWN
def test_sequence_orders_only_within_domain():
 assert compare_sequence(SequenceNumber("a",1),SequenceNumber("a",2)) is CausalRelation.BEFORE
