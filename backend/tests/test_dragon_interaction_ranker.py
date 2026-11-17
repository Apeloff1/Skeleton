"""Execute the actual five independently trained v4 models."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
import unittest

from skeleton.ai.webcrawler.dragon_specialist import DragonSpecialist,INTERACTION_SCHEMA
from skeleton.ai.webcrawler.dragon_specialist_search import contextual_features,interaction_features
from skeleton.ai.webcrawler.navigation_semantics import digest,tournament
from test_dragon_contextual_ranker import ContextualRankerTests

ROOT=Path(__file__).resolve().parents[2]
WEIGHTS=ROOT/"skeleton/ai/webcrawler/models/dragon_navigation_ranker.v4.json"


class InteractionRankerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=WEIGHTS.read_bytes()
        cls.pin=hashlib.sha256(raw).hexdigest()
        cls.model=DragonSpecialist.from_bytes(raw,cls.pin)

    def test_actual_parameter_count_and_independent_members(self):
        self.assertEqual(self.model.feature_count,50)
        self.assertEqual(len(self.model.ensemble),5)
        self.assertEqual(sum(sum(len(row) for row in w)+len(b)+len(v)
                             for w,b,v in self.model.ensemble),29120)
        self.assertEqual(len({digest(m) for m in self.model.ensemble}),5)

    def test_interaction_transform_and_no_external_inputs(self):
        low=(.2,.2,.3,.3,.9,1.,1.,.9,.8,.2)
        high=(.8,.7,.8,.8,.5,0.,0.,.1,.8,.9)
        context=contextual_features(high,[low,high])
        expanded=interaction_features(context)
        self.assertEqual(len(expanded),50)
        self.assertAlmostEqual(expanded[18],.3)
        self.assertAlmostEqual(expanded[19],.72)
        self.assertAlmostEqual(expanded[20],.63)
        self.assertAlmostEqual(expanded[28],.14)
        self.assertAlmostEqual(expanded[49],0.)
        self.assertGreater(self.model.score(expanded),
                           self.model.score(interaction_features(contextual_features(low,[low,high]))))

    def test_full_48_candidate_numerical_tournament(self):
        packet=ContextualRankerTests.packet(self,48);proofs=[]
        started=time.monotonic()
        def execute(group,role,first,stage):
            if role=="jeeves":return list(range(len(group["candidates"]),0,-1))
            rank,proof=self.model.rank(group,first)
            self.assertEqual(proof["architecture"],INTERACTION_SCHEMA)
            self.assertEqual(proof["member_count"],5)
            self.assertEqual(proof["output_digest"],digest(rank))
            self.assertTrue(proof["planner"]["interaction_features"])
            self.assertLessEqual(proof["planner"]["numeric_evaluations"],384)
            proofs.append(proof)
            return rank
        answer=tournament(packet,execute)
        self.assertEqual(answer["packet_digest"],packet["packet_digest"])
        self.assertEqual(len(proofs),9)
        print("DRAGON_V4_NUMERICAL_RECEIPT "+json.dumps({"members":5,"parameters":29120,
            "candidate_count":48,"specialist_matches":len(proofs),
            "numeric_evaluations":sum(p["planner"]["numeric_evaluations"] for p in proofs),
            "seconds":time.monotonic()-started,"live_jeeves_executed":False},sort_keys=True))

    def test_malformed_weights_and_replayed_members_rejected(self):
        value=json.loads(WEIGHTS.read_bytes())
        value["members"][1]=value["members"][0]
        raw=json.dumps(value,separators=(",",":")).encode()
        with self.assertRaises(ValueError):DragonSpecialist.from_bytes(raw,hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):self.model.score([.5]*18)


if __name__=="__main__":unittest.main()
