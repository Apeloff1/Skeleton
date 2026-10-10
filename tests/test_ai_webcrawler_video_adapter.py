import pytest
from skeleton.ai.webcrawler.video_adapter import VideoSourceGrant,VideoAdapterFrame,ingest_authorized_video
from skeleton.ai.webcrawler.video_memory_bridge import VideoIndexReceipt,commit_video_knowledge
from skeleton.ai.webcrawler.dragon_journal import DragonEventJournal
import sqlite3

class Frames:
    def observations(self,source_url):
        yield VideoAdapterFrame(0,1000,"transcript","The speaker introduces the topic",.95,"speech-0")
        yield VideoAdapterFrame(1000,2000,"frame_description","A diagram is shown",.8,"frame-1")

def test_explicit_video_permissions():
    source="https://example.org/lecture"
    with pytest.raises(PermissionError):
        ingest_authorized_video(VideoSourceGrant(source,False,allow_visual=True),Frames())
    with pytest.raises(PermissionError):
        ingest_authorized_video(VideoSourceGrant(source,True,allow_visual=False),Frames())
    chunks=ingest_authorized_video(VideoSourceGrant(source,True,allow_visual=True),Frames())
    assert len(chunks)==1
    assert chunks[0].modalities==("frame_description","transcript")

def test_video_memory_requires_real_persistence():
    chunks=ingest_authorized_video(VideoSourceGrant("https://example.org/v",True,allow_visual=True),Frames())
    journal=DragonEventJournal(sqlite3.connect(":memory:"))
    with pytest.raises(RuntimeError):
        commit_video_knowledge(journal,"s",chunks,lambda c:VideoIndexReceipt(c.chunk_id,False,0,""),now=1)
    assert not any(e["kind"]=="burn_complete" for e in journal.page("s")["events"])
    receipts=commit_video_knowledge(journal,"s",chunks,lambda c:VideoIndexReceipt(c.chunk_id,True,2,"prov-1"),now=2)
    assert receipts[0].persisted
    assert journal.verify("s")
    assert journal.page("s")["events"][-1]["payload"]["persisted"] is True
