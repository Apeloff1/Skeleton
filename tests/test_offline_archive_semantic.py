import hashlib
import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.app.offline_library import OfflineDocumentLibrary,OfflineLibraryError
from skeleton.app.offline_disk_index import DiskChunkWriter
from skeleton.app.offline_archive_semantic import ArchiveSemanticSearch,ArchiveSemanticPolicy
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy


def test_disk_spilled_archive_semantic_exact_offsets_and_revocation(tmp_path):
    enc=build_encoder(tmp_path)
    ranker=ContextualRanker(enc,SemanticPolicy(context_chars=128,min_cosine=.2))
    root=tmp_path/"ann";root.mkdir(mode=0o700)
    policy=ArchiveSemanticPolicy(leaf_chars=64,halo_chars=16)
    with OfflineDocumentLibrary(tmp_path/"library.sqlite") as lib:
        body="motor "*30+"cat "*20
        pin=hashlib.sha256(body.encode()).hexdigest()
        cursor=lib._db.execute("INSERT INTO offline_documents(root,relative_path,sha256,body,size_bytes) VALUES(?,?,?,?,?)",
            (str(tmp_path),"disk.txt",pin,"",len(body.encode())))
        writer=DiskChunkWriter(lib._db,cursor.lastrowid,256)
        writer.feed(body[:80]);writer.feed(body[80:]);writer.finish()
        adapter=ArchiveSemanticSearch(lib,ranker,policy)
        receipt=adapter.build(root,"one",DiskANNPolicy(shards=2,bands=4,bits=4,probes=5))
        adapter.attach(receipt["path"],receipt["manifest_sha256"])
        hits,proof=adapter.search("feline",limit=2)
        assert hits and any("cat" in h["excerpt"] for h in hits)
        assert all(body[h["char_start"]:h["char_end"]]==h["excerpt"] for h in hits)
        assert proof["verified_source_bytes"]==len(body.encode())
        lib._db.execute("UPDATE offline_documents SET sha256=? WHERE id=?",("a"*64,cursor.lastrowid))
        with pytest.raises(OfflineLibraryError,match="stale"):adapter.search("feline")
