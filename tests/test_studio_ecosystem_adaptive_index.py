from skeleton.ai.game_builder import studio_ecosystem_catalog as source

def test_catalog_index_budget_grows_with_live_ram_not_project_count(monkeypatch):
    monkeypatch.setattr(source,"_available_index_memory_bytes",lambda:64*1024*1024)
    assert source._adaptive_index_bytes()==2*1024*1024
    monkeypatch.setattr(source,"_available_index_memory_bytes",lambda:0)
    assert source._adaptive_index_bytes()==source.MAX_INDEX_BYTES
