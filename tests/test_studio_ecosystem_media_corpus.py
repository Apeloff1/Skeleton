from skeleton.ai.game_builder.studio_ecosystem_media_corpus import audit_original_studio_media_sources

def test_complete_catalog_can_be_audited_without_false_release_claims():
    report=audit_original_studio_media_sources()
    assert report["indexed_projects"]>=512
    assert report["renderable_source_projects"]+report["rejected_source_projects"]==report["indexed_projects"]
    assert len(report["source_chain_sha256"])==64
    assert not report["actual_media_rendered_for_all"]
    assert not report["release_certified"]

def test_corpus_receipt_is_deterministic():
    a=audit_original_studio_media_sources(max_error_details=1)
    b=audit_original_studio_media_sources(max_error_details=1)
    assert a["source_chain_sha256"]==b["source_chain_sha256"]
