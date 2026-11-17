"""Real quantized v5 weights, sparse arithmetic, and exact packet inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
import unittest

from skeleton.ai.webcrawler.dragon_specialist import DragonSpecialist, SPARSE_SCHEMA
from skeleton.ai.webcrawler.dragon_sparse_specialist import tile_indices, SIZE, TILES
from skeleton.ai.webcrawler.dragon_specialist_search import contextual_features, interaction_features
from skeleton.ai.webcrawler.navigation_semantics import digest,tournament
from test_dragon_contextual_ranker import ContextualRankerTests

ROOT=Path(__file__).resolve().parents[2]
WEIGHTS=ROOT/"skeleton/ai/webcrawler/models/dragon_navigation_ranker.v5.json"


class SparseRankerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=WEIGHTS.read_bytes()
        cls.pin=hashlib.sha256(raw).hexdigest()
        cls.model=DragonSpecialist.from_bytes(raw,cls.pin)

    def test_real_weight_capacity_and_sparsity(self):
        self.assertEqual(self.model.architecture,SPARSE_SCHEMA)
        self.assertEqual(self.model.feature_count,50)
        self.assertEqual(self.model.sparse.capacity,327690)
        self.assertGreater(self.model.sparse.nonzero,150000)
        self.assertLess(self.model.sparse.nonzero,self.model.sparse.capacity)
        self.assertEqual(self.model.sparse.receipt()["maximum_coefficient_terms_per_evaluation"],1470)
        self.assertEqual(len({hashlib.sha256(b.packed).hexdigest() for b in self.model.sparse.banks}),10)

    def test_unsigned_tile_reference(self):
        features=tuple((i%8)/8 for i in range(50))
        ids=tile_indices(features)
        self.assertEqual(len(ids),TILES)
        self.assertTrue(all(50<=i<SIZE for i in ids))
        self.assertEqual(ids,tile_indices(features))
        for k,expected in enumerate(ids):
            a,b,c=((k*17+3)%50,(k*29+11)%50,(k*37+23)%50)
            h=((k+1)*0x9e3779b1 ^ (int(features[a]*8)+1)*0x85ebca6b ^
               (int(features[b]*8)+1)*0xc2b2ae35 ^ (int(features[c]*8)+1)*0x27d4eb2f)&0xffffffff
            h=((h^(h>>16))*0x7feb352d)&0xffffffff
            h^=h>>15
            self.assertEqual(expected,50+h%(SIZE-50))
        with self.assertRaises(ValueError):tile_indices([1.1]*50)

    def test_full_tournament(self):
        packet=ContextualRankerTests.packet(self,48);proofs=[]
        started=time.monotonic()
        def execute(group,role,first,stage):
            if role=="jeeves":return list(range(len(group["candidates"]),0,-1))
            order,proof=self.model.rank(group,first)
            self.assertEqual(proof["architecture"],SPARSE_SCHEMA)
            self.assertEqual(proof["member_count"],10)
            self.assertEqual(proof["sparse_execution"]["allocated_coefficients"],327690)
            self.assertEqual(proof["execution_receipt_digest"],digest({k:v for k,v in proof.items() if k!="execution_receipt_digest"}))
            proofs.append(proof)
            return order
        result=tournament(packet,execute)
        self.assertEqual(result["packet_digest"],packet["packet_digest"])
        self.assertEqual(len(proofs),9)
        print("DRAGON_V5_SPARSE_RECEIPT "+json.dumps({"capacity":self.model.sparse.capacity,
            "nonzero":self.model.sparse.nonzero,"matches":len(proofs),
            "numeric_evaluations":sum(p["planner"]["numeric_evaluations"] for p in proofs),
            "seconds":time.monotonic()-started,"live_jeeves_executed":False},sort_keys=True))

    def test_malformed_quantized_artifact_held(self):
        value=json.loads(WEIGHTS.read_bytes())
        value["banks"][1]=value["banks"][0]
        raw=json.dumps(value,separators=(",",":")).encode()
        with self.assertRaises(ValueError):DragonSpecialist.from_bytes(raw,hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):self.model.score([0.]*18)


if __name__=="__main__":unittest.main()
