"""Microclimate-to-character response tests for rain, ice, pressure and heat."""
from __future__ import annotations

import unittest

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_weather_physics import (
    Microclimate, evolve_microclimate, WeatherCouplingError,
)
from skeleton.jeeves.game_frontier_motion import Weather
from skeleton.jeeves.game_frontier_ecosystem import AirConditions
from skeleton.jeeves.game_frontier_advanced_physics import (
    TractionSurface, Climber, evaluate_climbing,
)
from tests.test_game_frontier_advanced_scene import scene_params
from skeleton.jeeves.game_frontier import compile_frontier_scene


SURFACE = TractionSurface(Vec3(0,0,1),1.0,.75)
BASE = Microclimate(terrain_temperature_c=8,soil_water_fraction=.1,
                    ground_ice_fraction=0,loose_sediment_fraction=.1,
                    surface_roughness=.6,vegetation_cover=.3)


class WeatherTerrainTests(unittest.TestCase):
    def test_rain_makes_climbing_slippery_and_wet(self):
        rainy=Weather(Vec3(8,0,0),12,precipitation_mm_h=850,sunlight=.2)
        dry=Weather(Vec3(2,0,0),20,precipitation_mm_h=0,sunlight=1)
        a=evolve_microclimate(BASE,rainy,AirConditions(),SURFACE,delta_s=60)
        b=evolve_microclimate(BASE,dry,AirConditions(),SURFACE,delta_s=60)
        self.assertGreater(a.state.soil_water_fraction,b.state.soil_water_fraction)
        self.assertGreater(a.traction_surface.wetness,b.traction_surface.wetness)
        climber=Climber(80,100,.6,.8,.8)
        rain_grip=evaluate_climbing(a.traction_surface,climber)
        dry_grip=evaluate_climbing(b.traction_surface,climber)
        self.assertLess(rain_grip.effective_static_friction,
                        dry_grip.effective_static_friction)

    def test_frost_freeze_then_thaw_changes_ice(self):
        frost=Weather(Vec3(0,0,0),-20,precipitation_mm_h=500)
        cold=evolve_microclimate(BASE,frost,AirConditions(temperature_c=-20),
                                 SURFACE,delta_s=60)
        self.assertGreater(cold.state.ground_ice_fraction,0)
        self.assertGreater(cold.traction_surface.ice_fraction,0)
        warmth=Weather(Vec3(0,0,0),25,sunlight=1)
        thaw=evolve_microclimate(cold.state,warmth,
                                 AirConditions(temperature_c=25),
                                 SURFACE,delta_s=60)
        self.assertLess(thaw.state.ground_ice_fraction,
                        cold.state.ground_ice_fraction)

    def test_hot_ground_creates_updraft_and_pressure_wind(self):
        heat=Microclimate(terrain_temperature_c=42,soil_water_fraction=.1,
                          ground_ice_fraction=0,loose_sediment_fraction=.1,
                          surface_roughness=.2,vegetation_cover=.1,
                          pressure_gradient_pa_m=Vec3(-.5,0,0),
                          ground_heat_flux_w_m2=850)
        weather=Weather(Vec3(1,0,0),12)
        state=evolve_microclimate(heat,weather,
                                 AirConditions(temperature_c=12),
                                 SURFACE,delta_s=30)
        self.assertGreater(state.terrain_updraft.vertical_velocity_mps,0)
        self.assertGreater(state.pressure_wind_delta.x,0)
        self.assertGreater(state.air_density_kg_m3,0)

    def test_invalid_time_rejected(self):
        with self.assertRaises(WeatherCouplingError):
            evolve_microclimate(BASE,Weather(Vec3(0,0,0),15),
                                AirConditions(),SURFACE,delta_s=3600)

    def test_microclimate_feeds_scene_climbing_and_updraft(self):
        cfg=scene_params()
        warm=Microclimate(terrain_temperature_c=60,
                          soil_water_fraction=.9,ground_ice_fraction=.3,
                          loose_sediment_fraction=.6,surface_roughness=.5,
                          vegetation_cover=.2,ground_heat_flux_w_m2=400)
        cfg["advanced_microclimate"]=warm
        manifest=compile_frontier_scene(**cfg).manifest
        effect=manifest["advanced_physics"]["microclimate"]
        self.assertIsNotNone(effect)
        self.assertGreater(effect["updraft_mps"],0)
        self.assertGreater(manifest["advanced_physics"]["updraft_mps"],0)
        self.assertLess(manifest["advanced_physics"]["traction"]["max_slope_degrees"],
                        40)
        self.assertIn("realism_audit",manifest)


if __name__=="__main__":
    unittest.main()
