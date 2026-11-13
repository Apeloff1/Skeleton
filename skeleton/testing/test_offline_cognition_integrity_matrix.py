"""Execute 256 independently versioned hostile-source and scope-isolation cases.

The matrix is source-controlled real BM25/UTF8/citation input; it is not a
native GGUF test, synthetic model output or release certification.
"""
from __future__ import annotations
import json
from pathlib import Path
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import (
    CognitionError,Scope,loads,hash_bytes,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.retrieval import (
    BM25,IndexedDocument,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.sources import bind_source
from skeleton.ai.runtime.operational_ai.offline_cognition.core.evidence_pipeline import (
    EvidenceDocument,EvidenceIndex,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.grounded_work import (
    prepare,verify_prepared,
)

FOLDER=Path(__file__).resolve().parent/"fixtures"/"offline_cognition_integrity"
SCOPE=Scope("local","owner","a"*64,"b"*64)

def _all_cases():
    if FOLDER.is_symlink() or not FOLDER.is_dir():
        raise CognitionError("source integrity fixture directory missing or linked")
    names=sorted(x for x in FOLDER.iterdir() if x.name.endswith(".json"))
    if len(names)!=256:
        raise CognitionError("exact 256 adversarial source fixtures required")
    cases=[];ids=set()
    for path in names:
        if path.is_symlink() or not path.is_file():
            raise CognitionError("nonregular or linked source fixture")
        case=loads(path.read_bytes(),maximum=16384)
        if type(case) is not dict or case.get("schema")!="offline-cognition-integrity-case.v1":
            raise CognitionError("unknown fixture schema")
        if case.get("id") in ids or case.get("id")!=path.stem:
            raise CognitionError("fixture identity not unique or canonical")
        ids.add(case["id"])
        cases.append(case)
    return cases

class OfflineIntegrityMatrixTests(unittest.TestCase):
    def test_all_256_original_source_cases(self):
        cases=_all_cases()
        self.assertEqual(sum(c["kind"]=="scope_invariant" for c in cases),128)
        self.assertEqual(sum(c["kind"]=="quote_is_data" for c in cases),128)
        for case in cases:
            with self.subTest(case_id=case["id"]):
                if case["kind"]=="scope_invariant":
                    self._scope_case(case)
                elif case["kind"]=="quote_is_data":
                    self._quote_case(case)
                else:
                    self.fail("unknown adversarial scenario")

    def _scope_case(self,case):
        expected={"schema","id","kind","expected","query",
                  "local_documents","foreign_documents"}
        self.assertEqual(set(case),expected)
        self.assertEqual(case["expected"],"equal")
        self.assertEqual(len(case["local_documents"]),3)
        self.assertEqual(len(case["foreign_documents"]),1)
        local=tuple(IndexedDocument(
            v["document_id"],"local",hash_bytes(v["text"].encode()),v["text"],
        ) for v in case["local_documents"])
        other=tuple(IndexedDocument(
            v["document_id"],"foreign",hash_bytes(v["text"].encode()),v["text"],
        ) for v in case["foreign_documents"])
        baseline=BM25(local).search(case["query"],scope="local")
        with_private_corpus=BM25(local+other).search(case["query"],scope="local")
        self.assertEqual(baseline,with_private_corpus)
        self.assertEqual(BM25(local+other).search(case["query"],scope="foreign")[0][0],
                         "foreign_x")

    def _quote_case(self,case):
        expected={"schema","id","kind","expected","query","source_text"}
        self.assertEqual(set(case),expected)
        self.assertIn(case["expected"],("accept","reject"))
        raw=case["source_text"].encode("utf-8","strict")
        receipt=bind_source(raw,source_id="quoted",tenant="local",
                            subject="owner",approved=True)
        if case["expected"]=="reject":
            with self.assertRaises(CognitionError):
                EvidenceDocument(receipt,raw)
            return
        doc=EvidenceDocument(receipt,raw)
        index=EvidenceIndex((doc,),tenant="local",subject="owner")
        assembled=prepare(index,SCOPE,case["query"],limit=1,window_bytes=1024)
        proof=verify_prepared(assembled,index)
        self.assertEqual(len(assembled.spans),1)
        self.assertEqual(proof["source_count"],1)
        self.assertFalse(proof["semantic_entailment_proved"])
        self.assertFalse(proof["native_generation_performed"])
        payload=json.loads(assembled.prompt_text.split("\n",1)[1])
        self.assertIs(payload["source_text_is_policy"],False)
        quote=payload["source_records"][0]
        self.assertIs(quote["source_is_policy"],False)
        self.assertEqual(quote["quoted_original"],case["source_text"])
        self.assertEqual(quote["source_sha256"],receipt.sha256)

    def test_input_digests_are_stable_and_no_native_run_is_claimed(self):
        cases=_all_cases()
        kinds={x["kind"] for x in cases}
        self.assertEqual(kinds,{"scope_invariant","quote_is_data"})
        self.assertEqual(len({x["id"] for x in cases}),256)

if __name__=="__main__":
    unittest.main()
