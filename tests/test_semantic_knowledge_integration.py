import hashlib
import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy
from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
from skeleton.app.offline_knowledge import OfflineKnowledgeLibrary
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError


def test_semantic_library_preserves_exact_citation_and_scope(tmp_path):
    ranker=ContextualRanker(build_encoder(tmp_path),SemanticPolicy(context_chars=640,min_cosine=.35))
    with OfflineChatStore(tmp_path/"chat.sqlite") as store:
        library=OfflineKnowledgeLibrary(store,"a"*64,"b"*64,semantic_ranker=ranker)
        cats=library.add_text("animals","cat")
        motor=library.add_text("machines","motor")
        first=library.search("feline",limit=1)
        assert first[0]["document_id"]==cats["document_id"]
        assert first[0]["passage"]=="cat" and first[0]["char_start"]==0
        assert first[0]["document_sha256"]==hashlib.sha256(b"cat").hexdigest()
        assert all(x["document_id"]==motor["document_id"] for x in library.search("feline",document_ids=[motor["document_id"]]))
        library.delete(cats["document_id"])
        assert not store._db.execute("SELECT 1 FROM offline_semantic_vectors WHERE scope=?",(library._semantic_cache.scope,)).fetchone()
        with pytest.raises(RuntimeContractError,match="unavailable"):
            library.search("feline",document_ids=[cats["document_id"]])
