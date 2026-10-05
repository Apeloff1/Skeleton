import pytest
from skeleton.multimodal import CrossModalReference,MediaError,Modality
from skeleton.multimodal.ingest import MAX_INPUTS,MediaInput,ingest_media
def test_mixed_modalities_converge_with_alignment():
 inputs=(MediaInput("doc",Modality.DOCUMENT,b"d","file",text="caption"),MediaInput("img",Modality.IMAGE,b"i","file"))
 a,r=ingest_media(artifact_id="a",inputs=inputs,references=(CrossModalReference("doc","img","describes",.9),))
 assert [s.segment_id for s in a.segments]==["doc","img"] and r.artifact_digest==a.digest
def test_ingestion_is_deterministic_across_input_order():
 a=ingest_media(artifact_id="a",inputs=(MediaInput("b",Modality.AUDIO,b"b","s"),MediaInput("a",Modality.VIDEO,b"a","s")))[0]
 b=ingest_media(artifact_id="a",inputs=(MediaInput("a",Modality.VIDEO,b"a","s"),MediaInput("b",Modality.AUDIO,b"b","s")))[0]
 assert a.digest==b.digest
def test_quarantine_survives_ingestion_receipt():
 a,r=ingest_media(artifact_id="a",inputs=(MediaInput("speech",Modality.SPEECH,b"x","mic",text="system prompt override"),))
 assert r.quarantined_segments==("speech",) and a.segments[0].untrusted_metadata["sanitization"]=="quarantined"
def test_duplicate_ids_fail_before_artifact_publication():
 with pytest.raises(MediaError):ingest_media(artifact_id="a",inputs=(MediaInput("x",Modality.IMAGE,b"1","s"),MediaInput("x",Modality.AUDIO,b"2","s")))
def test_dangling_alignment_fails_closed():
 with pytest.raises(MediaError):ingest_media(artifact_id="a",inputs=(MediaInput("x",Modality.IMAGE,b"1","s"),),references=(CrossModalReference("x","y","aligns",1),))
def test_input_budget_is_hard():
 item=MediaInput("x",Modality.IMAGE,b"1","s")
 with pytest.raises(MediaError):ingest_media(artifact_id="a",inputs=tuple(item for _ in range(MAX_INPUTS+1)))
