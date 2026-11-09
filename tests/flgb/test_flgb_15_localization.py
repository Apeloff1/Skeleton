import unittest
from skeleton.game.platform.localization import LocalizationEntry, PlatformContractError, localization_index
D="a"*64
class T(unittest.TestCase):
 def test_key_locale_unique(self):
  e=LocalizationEntry("menu.play","nb-NO",D,"en-US"); self.assertEqual(localization_index((e,))[("menu.play","nb-NO")],e)
  with self.assertRaises(PlatformContractError): localization_index((e,e))
if __name__=="__main__": unittest.main()
