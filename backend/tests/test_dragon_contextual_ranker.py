"""Execute the actual v3 trained tensors and distribution-aware lookahead."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from skeleton.ai.webcrawler.dragon_specialist import DragonSpecialist,CONTEXTUAL_SCHEMA
from skeleton.ai.webcrawler.dragon_specialist_search import contextual_features
from skeleton.ai.webcrawler.navigation_semantics import digest,tournament,semantic_features

ROOT=Path(__file__).resolve().parents[2]
WEIGHTS=ROOT/"skeleton/ai/webcrawler/models/dragon_navigation_ranker.v3.json"


class ContextualRankerTests(unittest.TestCase):
    def setUp(self):
        raw=WEIGHTS.read_bytes()
        self.pin=hashlib.sha256(raw).hexdigest()
        self.model=DragonSpecialist.from_bytes(raw,self.pin)

    def test_exact_distribution_transform(self):
        low=(.2,.2,.3,.3,.9,1.,1.,.9,.8,.2)
        high=(.8,.7,.8,.8,.5,0.,0.,.1,.8,.9)
        x=contextual_features(high,[low,high])
        self.assertEqual(len(x),18)
        self.assertAlmostEqual(x[10],.65)
        self.assertAlmostEqual(x[11],.625)
        self.assertAlmostEqual(x[12],.675)
        self.assertAlmostEqual(x[13],.25)
        self.assertEqual(x[14:17],(1.,1.,.25))
        self.assertAlmostEqual(x[17],.7)
        self.assertEqual(x,contextual_features(high,[high,low]))
        self.assertGreater(self.model.score(x),self.model.score(contextual_features(low,[low,high])))

    def packet(self,count):
        terms=[["flight","navigation"],["garden","soil"],["flight","manual"],
          ["rendering","shader"],["aerodynamics","aircraft"],["navigation","route"],
          ["flight","advertisement"],["flight","landing"]]
        rows=[]
        for i in range(count):
            ts=terms[i%len(terms)]
            rows.append({"id":hashlib.sha256(str(i).encode()).hexdigest(),"terms":ts,
              "depth":i%3,"attempts":i%2,
              "semantic":round(semantic_features("flight navigation","https://fixture.example/"+"/".join(ts))["score"]*1000)})
        body={"snapshot_digest":"a"*64,"as_of":1700000000,"objective":["flight","navigation"],"candidates":rows}
        return {**body,"packet_digest":digest(body)}

    def test_full_tournament_actual_contextual_ranker_inference(self):
        packet=self.packet(48)
        proofs=[]
        def execute(group,role,first,stage):
            if role=="jeeves":
                return list(range(len(group["candidates"]),0,-1))
            rank,proof=self.model.rank(group,first)
            self.assertEqual(proof["architecture"],CONTEXTUAL_SCHEMA)
            self.assertEqual(proof["model_digest"],self.pin)
            self.assertEqual(proof["output_digest"],digest(rank))
            self.assertTrue(proof["planner"]["contextual_features"])
            self.assertLessEqual(proof["planner"]["numeric_evaluations"],384)
            self.assertGreater(proof["planner"]["distinct_contexts"],0)
            proofs.append(proof)
            return rank
        advice=tournament(packet,execute)
        self.assertEqual(len(proofs),9)
        self.assertEqual(advice["packet_digest"],packet["packet_digest"])

    def test_model_metric_tamper_and_width_rejection(self):
        with self.assertRaises(ValueError):self.model.score([.5]*10)
        value=json.loads(WEIGHTS.read_bytes())
        value["training"]["report"]["shifted_holdout"]["pair_accuracy"]=0.
        raw=json.dumps(value).encode()
        with self.assertRaises(ValueError):DragonSpecialist.from_bytes(raw,hashlib.sha256(raw).hexdigest())

    def test_small_and_full_candidate_groups(self):
        for n in (1,2,4,8):
            packet=self.packet(n);first=list(range(1,n+1))
            rank,receipt=self.model.rank(packet,first)
            self.assertEqual(sorted(rank),first)
            self.assertEqual(self.model.rank(packet,first),(rank,receipt))
            self.assertFalse(receipt["network_authorized"])


if __name__=="__main__":unittest.main()
