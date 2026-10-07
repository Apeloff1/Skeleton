from __future__ import annotations
import pytest
from skeleton.speech.runtime import *
def rt():return SpeechRuntime(SpeechSession("SESSION.1",1,SessionState.CONNECTED,2))
def test_provisional_transcript_never_commits_as_authoritative():assert rt().commit(TranscriptSegment("SESSION.1",1,0,"hel",SegmentState.PROVISIONAL)) is False
def test_final_segment_commits_once():
 r=rt();s=TranscriptSegment("SESSION.1",1,0,"hello",SegmentState.FINAL);assert r.commit(s)
 with pytest.raises(SpeechError,match="duplicate"):r.commit(s)
def test_reconnect_fences_old_frames():
 r=rt();r.reconnect()
 with pytest.raises(SpeechError,match="stale"):r.accept_frame(SpeechFrame("SESSION.1",1,0,0))
def test_backpressure_is_explicit():
 r=rt();r.accept_frame(SpeechFrame("SESSION.1",1,0,0));r.accept_frame(SpeechFrame("SESSION.1",1,1,20))
 with pytest.raises(SpeechError,match="backpressure"):r.accept_frame(SpeechFrame("SESSION.1",1,2,40))
def test_barge_in_cancels_buffered_output_path():r=rt();assert r.barge_in()=="tts_cancelled"
def test_cancel_is_terminal_for_reconnect():
 r=rt();r.cancel()
 with pytest.raises(SpeechError,match="terminal"):r.reconnect()
