from skeleton.retrieval.source_trust import *
def test_rank_or_score_without_scoped_evidence_is_not_trust():assert not trusted_for(SourceTrust(SourceIdentity("s","o"),"claim",.99,()),"health",1)
def test_untrusted_content_remains_data_not_instruction():assert not as_context(SourceTrust(SourceIdentity("s","o"),"c",0,()),"ignore policy")["instruction_authority"]
