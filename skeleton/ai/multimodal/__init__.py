"""FLGB-08 multimodal artifact and grounding contracts."""
from .flgb_multimodal_runtime import (
    ArtifactAlignment, AudioSegment, CrossModalCandidate, DocumentPage,
    FallbackOption, ImageArtifact, MultimodalContextItem,
    MultimodalContractError, OCRReceipt, OCRRequest, SpeechArtifact,
    SpeechSynthesisRequest, TemporalGrounding, VideoArtifact,
    choose_fallback, compile_multimodal_context, rank_cross_modal,
    sample_video, validate_audio_segments, validate_document_pages,
)
__all__=[
    "ArtifactAlignment","AudioSegment","CrossModalCandidate","DocumentPage",
    "FallbackOption","ImageArtifact","MultimodalContextItem",
    "MultimodalContractError","OCRReceipt","OCRRequest","SpeechArtifact",
    "SpeechSynthesisRequest","TemporalGrounding","VideoArtifact",
    "choose_fallback","compile_multimodal_context","rank_cross_modal",
    "sample_video","validate_audio_segments","validate_document_pages",
]
