import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError


def test_ann_integration_rechecks_canonical_leaf_and_revision(tmp_path):
    ranker=ContextualRanker(build_encoder(tmp_path),SemanticPolicy(context_chars=640,min_cosine=.2))
    root=tmp_path/"ann";root.mkdir(mode=0o700)
    with OfflineChatStore(tmp_path/"chat.sqlite") as store:
        library=OfflineKnowledgeLibrary(store,"a"*64,"b"*64,semantic_ranker=ranker)
        cat=library.add_text("cat topic","cat")
        motor=library.add_text("motor topic","motor")
        proof=library.build_semantic_ann(root,"g1",DiskANNPolicy(shards=2,workers=2,bands=8,bits=4,probes=5))
        library.attach_semantic_ann(proof["path"],proof["manifest_sha256"])
        hits=library.search("feline",limit=1)
        assert hits[0]["passage"]=="cat" and hits[0]["document_id"]==cat["document_id"]
        assert all(h["document_id"]==motor["document_id"] for h in library.search("motor",document_ids=[motor["document_id"]]))
        library.delete(cat["document_id"])
        with pytest.raises(RuntimeContractError,match="stale"):
            library.search("feline")
