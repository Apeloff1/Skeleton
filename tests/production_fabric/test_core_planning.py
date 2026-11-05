import unittest
from skeleton.ai.runtime.production_fabric.planning.routes import shortest
from skeleton.ai.runtime.production_fabric.planning.quests import Quest, compile_quests
from skeleton.ai.runtime.production_fabric.planning.encounters import Combatant, strike
from skeleton.ai.runtime.production_fabric.planning.economy import exchange
from skeleton.ai.runtime.production_fabric.planning.weather import evolve
from skeleton.ai.runtime.production_fabric.planning.abilities import activate
from skeleton.ai.runtime.production_fabric.planning.spawns import place
from skeleton.ai.runtime.production_fabric.planning.strategies import plan
from skeleton.ai.runtime.production_fabric.planning.worlds import validate_playable
from skeleton.ai.runtime.production_fabric.contracts.spec import parse_world
from skeleton.ai.runtime.production_fabric.contracts.errors import ConflictError, ContractError
from skeleton.ai.runtime.production_fabric.product.content.worlds.cloudbreak_signal import WORLD

class PlanningTests(unittest.TestCase):

    def test_shortest_weighted_route(self):
        g = {'a': {'b': 1, 'c': 10}, 'b': {'c': 2}, 'c': {}}
        self.assertEqual(shortest(g, 'a', 'c')['path'], ['a', 'b', 'c'])
        self.assertEqual(shortest(g, 'a', 'c', blocked={'b'})['cost'], 10)

    def test_quest_cycles_denied(self):
        with self.assertRaises(ContractError):
            compile_quests([Quest('a', ('b',), (), ()), Quest('b', ('a',), (), ())])

    def test_combat_damage_bounded(self):
        enemy = Combatant('enemy', 10, 2, 1, 3)
        hit, receipt = strike(Combatant('hero', 10, 5, 0, 4), enemy)
        self.assertEqual(hit.health, 6)
        self.assertEqual(receipt['damage'], 4)

    def test_atomic_trade(self):
        with self.assertRaises(ConflictError):
            exchange({'coin': 1}, spend={'coin': 2}, receive={'gem': 1})
        self.assertEqual(exchange({'coin': 3}, spend={'coin': 2}, receive={'gem': 1}), {'coin': 1, 'gem': 1})

    def test_weather_reproducible(self):
        self.assertEqual(evolve('clear', 123), evolve('clear', 123))

    def test_ability_cooldown(self):
        state = activate('wind', 1, 5, {'points': 10, 'ready': {}}, tick=1)
        with self.assertRaises(ConflictError):
            activate('wind', 1, 5, state, tick=2)

    def test_spawn_no_overlap(self):
        self.assertEqual(place(2, 2, {(0, 0)}, seed=0), (1, 0))

    def test_plan_dependency(self):
        self.assertEqual(plan({'a': [], 'b': ['a'], 'c': ['b']}, 'c'), ['a', 'b', 'c'])

    def test_world_is_structurally_playable(self):
        self.assertTrue(validate_playable(parse_world(WORLD)))
