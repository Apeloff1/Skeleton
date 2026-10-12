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
                                "modalities":chunk.modalities})
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
