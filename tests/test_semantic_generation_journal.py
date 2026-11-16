import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.app.offline_semantic_journal import SemanticIndexJournal


def test_managed_publication_restart_and_incremental_refresh(tmp_path):
    ranker=ContextualRanker(build_encoder(tmp_path),SemanticPolicy(context_chars=640,min_cosine=.2))
    root=tmp_path/"index";root.mkdir(mode=0o700)
    path=tmp_path/"chat.sqlite"
    policy=DiskANNPolicy(shards=2,bands=4,bits=4,probes=5)
    with OfflineChatStore(path) as store:
        lib=OfflineKnowledgeLibrary(store,"a"*64,"b"*64,semantic_ranker=ranker)
        lib.add_text("cat","cat")
        journal=SemanticIndexJournal(lib,root)
        first=journal.refresh(policy)
        assert first["active_revision"]==1
    with OfflineChatStore(path) as store:
        lib=OfflineKnowledgeLibrary(store,"a"*64,"b"*64,semantic_ranker=ranker)
        journal=SemanticIndexJournal(lib,root)
        assert journal.attach().revision==1
        assert lib.search("feline")[0]["passage"]=="cat"
        lib.add_text("motor","motor")
        with pytest.raises(RuntimeContractError,match="stale"):lib.search("feline")
        second=journal.refresh(policy)
        assert second["active_revision"]==2 and second["reused_dense"]==1
        assert {x["status"] for x in journal.history()}=={"active","historical"}
        assert lib.search("motor")[0]["passage"]=="motor"
