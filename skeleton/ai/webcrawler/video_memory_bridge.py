"""Video digestion handoff to dragon journal; indexing receipt remains authoritative."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from .video_digest import VideoKnowledgeChunk
from .dragon_journal import DragonEventJournal

@dataclass(frozen=True)
class VideoIndexReceipt:
    chunk_id:str
    persisted:bool
    index_revision:int
    provenance_id:str

def commit_video_knowledge(journal:DragonEventJournal,session_id:str,
                           chunks:tuple[VideoKnowledgeChunk,...],
                           persist:Callable[[VideoKnowledgeChunk],VideoIndexReceipt],
                           *,now:float)->tuple[VideoIndexReceipt,...]:
    receipts=[]
    for chunk in chunks:
        journal.append(session_id,"acquisition_accepted",chunk.source_url,at=now,
                       payload={"video_chunk_id":chunk.chunk_id,"start_ms":chunk.start_ms,"end_ms":chunk.end_ms,
                                "modalities":list(chunk.modalities)})
        journal.append(session_id,"burn_started",chunk.source_url,at=now,
                       payload={"video_chunk_id":chunk.chunk_id})
        receipt=persist(chunk)
        if receipt.chunk_id!=chunk.chunk_id or not receipt.persisted or receipt.index_revision<0 or not receipt.provenance_id:
            raise RuntimeError("video index persistence receipt missing or invalid")
        journal.append(session_id,"burn_complete",chunk.source_url,at=now,
                       payload={"persisted":True,"video_chunk_id":chunk.chunk_id,
                                "index_revision":receipt.index_revision,"provenance_id":receipt.provenance_id})
        receipts.append(receipt)
    return tuple(receipts)

def seal_video_distillation(journal:DragonEventJournal,session_id:str,*,
                            source_url:str,chunk_id:str,distilled:bool,now:float):
    """Record distillation only after a separate durable burn receipt exists."""
    if distilled is not True or not chunk_id or not source_url:
        raise RuntimeError("distillation receipt missing or invalid")
    burned=False
    sealed=False
    after=0
    while True:
        page=journal.page(session_id,after=after,limit=1000)
        for event in page["events"]:
            payload=event["payload"]
            if payload.get("video_chunk_id")!=chunk_id or event["url"]!=source_url:
                continue
            if event["kind"]=="burn_complete" and payload.get("persisted") is True:
                burned=True
            if event["kind"]=="distill_complete":
                sealed=True
        if not page["hasMore"]:
            break
        after=int(page["nextCursor"])
    if not burned:
        raise RuntimeError("distillation requires a completed burn")
    if sealed:
        raise RuntimeError("distillation already sealed")
    return journal.append(session_id,"distill_complete",source_url,at=now,
                          payload={"distilled":True,"video_chunk_id":chunk_id})
