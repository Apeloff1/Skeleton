import unittest
from skeleton.game.render.particle_vfx import ParticleEmitter
D="a"*64

class TestParticleVFX(unittest.TestCase):
    def test_emission_is_integer_and_capped(self):
        emitter=ParticleEmitter("fire",D,2000,3,1000)
        self.assertEqual(emitter.emitted_count(500),1)
        self.assertEqual(emitter.emitted_count(5000),3)

if __name__=="__main__": unittest.main()
