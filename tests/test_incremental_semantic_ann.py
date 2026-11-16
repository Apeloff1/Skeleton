import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy
from skeleton.retrieval.disk_semantic_ann import DiskANN,DiskANNPolicy
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary


def test_incremental_generation_reuses_only_exact_surviving_vectors(tmp_path):
    ranker=ContextualRanker(build_encoder(tmp_path),SemanticPolicy(context_chars=640,min_cosine=.2))
    root=tmp_path/"index";root.mkdir(mode=0o700)
    policy=DiskANNPolicy(shards=2,bands=4,bits=4,probes=5)
    with OfflineChatStore(tmp_path/"chat.sqlite") as store:
        lib=OfflineKnowledgeLibrary(store,"a"*64,"b"*64,semantic_ranker=ranker)
        old=lib.add_text("old","cat")
        keep=lib.add_text("keep","motor")
        first=lib.build_semantic_ann(root,"one",policy)
        first_index=DiskANN(first["path"],first["manifest_sha256"],expected_space=ranker.identity,expected_snapshot=lib.semantic_source_snapshot())
        lib.delete(old["document_id"])
        fresh=lib.add_text("new","feline")
        second=lib.build_semantic_ann(root,"two",policy,previous=first_index)
        assert second["reused_dense"]==1 and second["encoded_dense"]==1
        assert second["previous_manifest_sha256"]==first["manifest_sha256"]
        lib.attach_semantic_ann(second["path"],second["manifest_sha256"])
        assert lib.search("feline",limit=1)[0]["document_id"]==fresh["document_id"]
        assert all(h["document_id"]!=old["document_id"] for h in lib.search("cat"))
