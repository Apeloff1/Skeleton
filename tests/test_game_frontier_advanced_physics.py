"""Physically grounded reference acceptance checks for frontier aero and contact.

These tests distinguish observable invariants from true CFD/native validation.
"""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_ecosystem import AirConditions
from skeleton.jeeves.game_frontier_advanced_physics import (
    AdvancedPhysicsError, RigidBody, AeroProfile, WakeSource, UpdraftColumn,
    airflow_at, terminal_velocity, integrate_air_motion,
    TractionSurface, Climber, evaluate_climbing,
    CollisionContact, resolve_contact, aggregate_realism,
    kinetic_energy, ZERO,
)


class TerminalVelocityTests(unittest.TestCase):
    def test_terminal_velocity_mass_area_density_and_altitude(self):
        tv = terminal_velocity(80, 1.2, 1.0, .7)
        self.assertAlmostEqual(tv, math.sqrt(2*80*9.80665/(1.2*.7)),places=8)
        self.assertGreater(terminal_velocity(160,1.2,1,.7),tv)
        self.assertLess(terminal_velocity(80,1.2,1,1.4),tv)
        sea = airflow_at(ZERO, ambient_wind=ZERO,
                         air=AirConditions(altitude_m=0, temperature_c=20))
        mountain = airflow_at(ZERO, ambient_wind=ZERO,
                              air=AirConditions(altitude_m=3000, temperature_c=20))
        self.assertLess(mountain.air_density_kg_m3,sea.air_density_kg_m3)
        self.assertGreater(terminal_velocity(80,mountain.air_density_kg_m3,1,.7),
                           terminal_velocity(80,sea.air_density_kg_m3,1,.7))

    def test_air_drag_opposes_relative_velocity_and_converges(self):
        body=RigidBody("jumper",Vec3(0,0,500),Vec3(0,0,-80),80,.4)
        env=airflow_at(body.position, ambient_wind=ZERO,
                       air=AirConditions(altitude_m=830,temperature_c=18))
        model=AeroProfile(1.,.7)
        step=integrate_air_motion(body,model,env,delta_s=.05)
        self.assertGreater(step.body.velocity.z,body.velocity.z)
        self.assertGreater(step.drag_force_n.z,0)
        self.assertGreaterEqual(step.drag_dissipation_j,0)

    def test_thermal_and_drafting_change_air_flow_and_fall(self):
        ambient=Vec3(12,0,0)
        params=dict(ambient_wind=ambient, air=AirConditions(
            altitude_m=830,temperature_c=20),
            wakes=(WakeSource("tower",ZERO,4,.75,25),),
            thermals=(UpdraftColumn(Vec3(0,0,0),8,6,200),),
            turbulence_seed=777,turbulence_amplitude=1,time_s=2)
        lee=airflow_at(Vec3(4,0,20),**params)
        upstream=airflow_at(Vec3(-4,0,20),**params)
        self.assertLess(lee.wake_drag_multiplier,upstream.wake_drag_multiplier)
        self.assertGreater(lee.updraft_mps,0)
        self.assertEqual(lee,airflow_at(Vec3(4,0,20),**params))
        high=airflow_at(Vec3(4,0,220),**params)
        self.assertEqual(high.updraft_mps,0)
        body=RigidBody("drift",Vec3(4,0,20),Vec3(0,0,-30),75,.4)
        still=airflow_at(body.position, ambient_wind=ZERO,
                          air=AirConditions(altitude_m=830))
        up=integrate_air_motion(body,AeroProfile(1.,1.0),lee,delta_s=.05)
        no=integrate_air_motion(body,AeroProfile(1.,1.0),still,delta_s=.05)
        self.assertGreater(up.body.velocity.z,no.body.velocity.z)

    def test_rejects_nan_and_bad_kinematics(self):
        with self.assertRaises(AdvancedPhysicsError):
            terminal_velocity(0,1,1,1)
        with self.assertRaises(AdvancedPhysicsError):
            AeroProfile(float("nan"),1)
        with self.assertRaises(AdvancedPhysicsError):
            RigidBody("jumper",ZERO,ZERO,0,.5)


class TractionClimbingTests(unittest.TestCase):
    @staticmethod
    def slope(degrees, **kwargs):
        theta=math.radians(degrees)
        return TractionSurface(Vec3(math.sin(theta),0,math.cos(theta)),
                               1.1,.8,**kwargs)

    def test_slope_wet_ice_and_gravel_reduce_traction(self):
        character=Climber(80,300,.65,.9,.9,load_kg=15)
        dry=evaluate_climbing(self.slope(30),character)
        iced=evaluate_climbing(self.slope(30,wetness=1,ice_fraction=.9,
                                             loose_gravel=.5),character)
        self.assertGreater(dry.effective_static_friction,iced.effective_static_friction)
        self.assertGreater(dry.recommended_speed_scale,iced.recommended_speed_scale)
        self.assertGreater(iced.slip_risk,dry.slip_risk)

    def test_vertical_requires_real_footholds_or_rope(self):
        wall=self.slope(90,foothold_quality=1)
        climber=Climber(70,1600,1,1,1)
        supported=evaluate_climbing(wall,climber)
        unaided=evaluate_climbing(wall,replace(climber,strength_n=0))
        self.assertTrue(supported.climbing_possible)
        self.assertFalse(unaided.climbing_possible)
        self.assertEqual(supported.recommended_gait,"climb")

    def test_cargo_and_wind_increase_load(self):
        slope=self.slope(35)
        climber=Climber(70,100,.7,.8,.8,load_kg=0)
        plain=evaluate_climbing(slope,climber)
        burdened=evaluate_climbing(slope,replace(climber,load_kg=50),
                                   wind=Vec3(25,0,0))
        self.assertGreater(burdened.required_uphill_force_n,
                           plain.required_uphill_force_n)


class ContactTests(unittest.TestCase):
    def test_two_body_central_head_on_conserves_linear_momentum(self):
        a=RigidBody("heavy",Vec3(0,0,0),Vec3(5,0,0),100,.5,
                    restitution=.5,friction=0)
        b=RigidBody("light",Vec3(1,0,0),Vec3(-2,0,0),20,.5,
                    restitution=.5,friction=0)
        c=CollisionContact(Vec3(.5,0,0),Vec3(1,0,0),.1,
                           surface_restitution=.5)
        result=resolve_contact(a,b,c)
        self.assertGreater(result.normal_impulse_ns,0)
        self.assertAlmostEqual(result.momentum_residual_ns,0,places=8)
        self.assertLessEqual(result.energy_after_j,result.energy_before_j+1e-8)
        self.assertLess(result.body_a.velocity.x,5)
        self.assertGreater(result.body_b.velocity.x,-2)
        self.assertGreater(result.body_b.position.x,b.position.x)

    def test_weight_changes_impact_momentum_transfer(self):
        a=RigidBody("A",Vec3(0,0,0),Vec3(10,0,0),10,.5,
                    restitution=0,friction=0)
        heavy=RigidBody("B",Vec3(1,0,0),ZERO,100,.5,
                        restitution=0,friction=0)
        light=replace(heavy,mass_kg=10)
        contact=CollisionContact(Vec3(.5,0,0),Vec3(1,0,0),0)
        shock_heavy=resolve_contact(a,heavy,contact)
        shock_light=resolve_contact(a,light,contact)
        self.assertGreater(shock_heavy.normal_impulse_ns,shock_light.normal_impulse_ns)
        self.assertGreater(shock_heavy.energy_dissipated_j,
                           shock_light.energy_dissipated_j)

    def test_off_centre_friction_generates_spin(self):
        a=RigidBody("A",Vec3(0,0,0),Vec3(3,2,0),20,.5,
                    restitution=.1,friction=.8)
        b=RigidBody("B",Vec3(1,0,0),ZERO,20,.5,
                    restitution=.1,friction=.8)
        c=CollisionContact(Vec3(.5,.15,0),Vec3(1,0,0),.02)
        out=resolve_contact(a,b,c)
        self.assertGreater(out.friction_impulse_ns,0)
        self.assertGreater(abs(out.body_a.angular_velocity.z),0)
        self.assertLessEqual(out.energy_after_j,out.energy_before_j+1e-7)
        self.assertAlmostEqual(out.momentum_residual_ns,0,places=7)

    def test_static_ground_support(self):
        a=RigidBody("falling",Vec3(0,0,.4),Vec3(0,0,-10),75,.5,
                    restitution=0)
        contact=CollisionContact(Vec3(0,0,0),Vec3(0,0,-1),.1,
                                 surface_restitution=0)
        out=resolve_contact(a,None,contact)
        self.assertGreater(out.body_a.velocity.z,a.velocity.z)
        self.assertGreater(out.body_a.position.z,a.position.z)
        self.assertGreater(out.energy_dissipated_j,0)

    def test_aggregated_realism_receipts_are_reproducible(self):
        body=RigidBody("walker",Vec3(0,0,4),Vec3(0,0,-4),65,.5)
        wind=airflow_at(body.position,ambient_wind=Vec3(2,0,2),
                        air=AirConditions(altitude_m=830),turbulence_seed=2)
        aero=integrate_air_motion(body,AeroProfile(1.,.7),wind,delta_s=.05)
        terrain=TractionSurface(Vec3(0,0,1),.8,.7,wetness=.3)
        decision=evaluate_climbing(terrain,Climber(65,400,.6,.8,.9))
        first=aggregate_realism(aero,wind,decision,terrain)
        self.assertEqual(first,aggregate_realism(aero,wind,decision,terrain))
        self.assertEqual(len(first.evidence_digest),64)
        self.assertGreater(first.air_density_kg_m3,0)
        self.assertTrue(first.collision_energy_nonincreasing)


if __name__=="__main__":
    unittest.main()
