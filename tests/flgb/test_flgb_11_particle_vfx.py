import unittest
from skeleton.game.render.particle_vfx import ParticleEmitter
D="a"*64

class TestParticleVFX(unittest.TestCase):
    def test_particle_spawn_respects_capacity(self):
        emitter=ParticleEmitter("e",100,100000,7,D)
        self.assertEqual(emitter.spawn_count(1000,0),100)
        self.assertEqual(emitter.spawn_count(1000,90),10)

if __name__=="__main__": unittest.main()
