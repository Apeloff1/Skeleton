import unittest
from skeleton.game.gameplay.economy_rules import EconomyRule, GameplayContractError
class T(unittest.TestCase):
 def test_transfer_bounds(self):
  r=EconomyRule("gold",0,1000,100)
  self.assertEqual(r.transfer(200,300,50),(150,350))
  with self.assertRaises(GameplayContractError): r.transfer(20,990,50)
if __name__=="__main__": unittest.main()
