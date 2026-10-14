import pytest
from skeleton.ai.webcrawler.video_digest import VideoObservation,digest_video_observations
from skeleton.ai.webcrawler.video_stream import VideoStreamSession

def o(start,end,modality,text,source="s",confidence=.9):
    return VideoObservation(start,end,modality,text,confidence,source)

def test_multimodal_digestion_preserves_time_and_evidence():
    observations=[o(2000,4000,"frame_description","Dragon on screen","frame-1"),o(1000,3000,"transcript","Dragon explains memory","speech-1")]
    chunks=digest_video_observations("https://example.org/video",observations)
    assert len(chunks)==1
    assert chunks[0].start_ms==1000 and chunks[0].end_ms==4000
    assert chunks[0].modalities==("frame_description","transcript")
    assert chunks[0].chunk_id==digest_video_observations("https://example.org/video",reversed(observations))[0].chunk_id

def test_stream_flush_and_close():
    session=VideoStreamSession("https://example.org/live",window_ms=10000,max_lateness_ms=1000)
    session.push(o(0,1000,"transcript","first"))
    session.push(o(25000,26000,"ocr","later"))
    ready=session.flush_ready()
    assert len(ready)==1 and "first" in ready[0].text
    remaining=session.close()
    assert len(remaining)==1 and "later" in remaining[0].text
    with pytest.raises(RuntimeError):session.push(o(27000,28000,"transcript","closed"))

def test_invalid_evidence_and_budget_fail_closed():
    with pytest.raises(ValueError):digest_video_observations("https://example.org/v",[o(0,1,"transcript","a",confidence=float("nan"))])
    with pytest.raises(ValueError):digest_video_observations("https://example.org/v",[o(0,1,"unverified","a")])
    session=VideoStreamSession("https://example.org/v",max_observations=1)
    session.push(o(0,1,"transcript","first"))
    with pytest.raises(ValueError):session.push(o(1,2,"transcript","second"))
