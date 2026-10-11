"""Real original professions, bounded markets and observed-only rumors."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.npc_society_runtime import (
    make_society, apply_world_event,
)
from skeleton.ai.game_builder.npc_social_economy import (
    EconomyError,new_economy,price,produce_goods,transact,
    diffuse_witnessed_memory,citizen_dialogue,
)


class NPCEconomyKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world=forge_director(
            "living_economy",seed=7117,
            regions=tuple(f"region_{n:02d}" for n in range(12)),
            quest_types=("main_story","profession","regional_story"),
            stages=2,
        )

    def test_authored_professions_transform_real_inventory_resources(self):
        society=make_society(self.world,48,authorized=True)
        index=next(i for i,p in enumerate(society.profiles)
                   if p.profession=="builder")
        p=society.profiles[index]
        minds=list(society.minds)
        minds[index]=replace(minds[index],intent="work",scene=p.workplace)
        working=replace(society,minds=tuple(minds),turn=6)
        before=new_economy(working,authorized=True)
        after=produce_goods(before,working,authorized=True)
        a=dict(after.accounts[index].goods)
        b=dict(before.accounts[index].goods)
        self.assertEqual(a["wood"],b["wood"]-1)
        self.assertEqual(a["tools"],b["tools"]+1)
        self.assertEqual(after.events[-1].kind,"produce")
        self.assertEqual(after.digest,produce_goods(
            before,working,authorized=True).digest)

    def test_money_and_materials_are_conserved_by_real_colocated_trade(self):
        society=make_society(self.world,36,authorized=True)
        seller=society.profiles[0].key
        buyer=society.profiles[12].key
        self.assertEqual(society.minds[0].scene,society.minds[12].scene)
        market=new_economy(society,authorized=True)
        site=society.minds[0].scene
        locals=tuple(m.key for m in society.minds if m.scene==site)
        total_currency=sum(a.coins for a in market.accounts)
        total_grain=sum(dict(a.goods)["grain"] for a in market.accounts)
        rate=price(market,"grain",region_keys=locals)
        exchanged=transact(market,society,seller=seller,buyer=buyer,
                           resource="grain",quantity=1,authorized=True)
        self.assertEqual(sum(a.coins for a in exchanged.accounts),total_currency)
        self.assertEqual(sum(dict(a.goods)["grain"] for a in exchanged.accounts),
                         total_grain)
        self.assertEqual(exchanged.events[-1].coins,rate)
        self.assertEqual(exchanged.events[-1].amount,1)
        self.assertNotEqual(exchanged.digest,market.digest)

    def test_no_phantom_assets_teleport_trade_or_infinite_currency(self):
        society=make_society(self.world,24,authorized=True)
        market=new_economy(society,authorized=True)
        with self.assertRaises(EconomyError):
            transact(market,society,seller=society.profiles[0].key,
                     buyer=society.profiles[1].key,resource="ore",
                     quantity=1,authorized=True)
        with self.assertRaises(EconomyError):
            transact(market,society,seller=society.profiles[0].key,
                     buyer=society.profiles[12].key,resource="artwork",
                     quantity=1,authorized=True)
        with self.assertRaises(PermissionError):
            transact(market,society,seller=society.profiles[0].key,
                     buyer=society.profiles[12].key,resource="grain",
                     quantity=1,authorized=False)
        with self.assertRaises(EconomyError):
            price(market,"fictional_asset",region_keys=())

    def test_firsthand_and_secondhand_memory_have_different_certainty(self):
        society=make_society(self.world,36,authorized=True)
        source=society.profiles[0].key
        listener=society.profiles[12].key
        event=apply_world_event(
            society,self.world,event="hero_saved_village",
            subject="hero",scene=society.minds[0].scene,valence=80,
            witnesses=(source,),authorized=True,
        )
        self.assertEqual(event.minds[0].memories[0].origin,"observed")
        self.assertEqual(event.minds[12].memories,())
        shared=diffuse_witnessed_memory(event,subject="hero",
                                       max_recipients=5,authorized=True)
        heard=next(x for x in shared.minds[12].memories
                   if x.event=="hero_saved_village")
        self.assertEqual(heard.origin,"rumor")
        self.assertEqual(heard.certainty,75)
        self.assertLess(heard.valence,event.minds[0].memories[0].valence)
        self.assertEqual(shared.minds[1].memories,())
        self.assertEqual(diffuse_witnessed_memory(
            shared,subject="hero",max_recipients=5,
            authorized=True).minds[12].memories,
            shared.minds[12].memories)
        speaker=citizen_dialogue(shared,listener)
        self.assertEqual(speaker["attitude"],"welcoming")
        self.assertIn("I heard about",speaker["line"])
        self.assertFalse(speaker["language_model_generated"])
        speaker2=citizen_dialogue(shared,source)
        self.assertIn("I saw",speaker2["line"])

    def test_rumors_do_not_reach_unseen_regions_or_skip_permission(self):
        society=make_society(self.world,36,authorized=True)
        with self.assertRaises(PermissionError):
            diffuse_witnessed_memory(society,subject="hero",authorized=False)
        self.assertEqual(diffuse_witnessed_memory(
            society,subject="hero",authorized=True).digest,society.digest
            if society.latest_event=="rumor_diffusion" else
            replace(society,latest_event="rumor_diffusion").digest)
        with self.assertRaises(EconomyError):
            citizen_dialogue(society,"invented_actor")


if __name__=="__main__":
    unittest.main()
