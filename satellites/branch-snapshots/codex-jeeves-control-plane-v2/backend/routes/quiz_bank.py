"""
╭───────────────────────────────────────────────────────────────────────────╮
│              CODEDOCK COMPREHENSIVE QUIZ BANK v11.6 SOTA                  │
│                                                                           │
│  285 Industry-Standard Quizzes (95 per subject)                           │
│  Progressive Difficulty: Easy → Medium → Hard → Expert → Mastery          │
│  - Physics: Mechanics, Collisions, Fluids, Particles, Constraints         │
│  - Math: Linear Algebra, Calculus, Geometry, Noise, Interpolation         │
│  - CS: Data Structures, Algorithms, Graphics, AI, Networking              │
│                                                                           │
│  Difficulty Distribution per Subject (95 questions each):                 │
│  - Easy (diff=1): 20 questions - Foundation concepts                      │
│  - Medium (diff=2): 25 questions - Applied understanding                  │
│  - Hard (diff=3): 25 questions - Complex problem solving                  │
│  - Expert (diff=4): 15 questions - Advanced integration                   │
│  - Mastery (diff=5): 10 questions - Industry-level competency             │
╰───────────────────────────────────────────────────────────────────────────╯
"""

from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
import random
import uuid
import os

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/quiz-bank", tags=["Comprehensive Quiz Bank"])

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
mongo_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
quiz_db = mongo_client.codedock_quizzes

# ============================================================================
# PHYSICS QUIZ BANK - 95 Questions
# ============================================================================

PHYSICS_QUIZZES = [
    # Classical Mechanics (20)
    {"q": "What is Newton's First Law also known as?", "type": "mc", "opts": ["Law of Inertia", "Law of Acceleration", "Law of Reaction", "Law of Gravity"], "ans": "Law of Inertia", "exp": "Newton's First Law states that an object at rest stays at rest, and an object in motion stays in motion unless acted upon by an external force.", "cat": "mechanics", "diff": 1},
    {"q": "F = ma represents which law?", "type": "mc", "opts": ["Newton's First Law", "Newton's Second Law", "Newton's Third Law", "Law of Conservation"], "ans": "Newton's Second Law", "exp": "Force equals mass times acceleration is the mathematical form of Newton's Second Law.", "cat": "mechanics", "diff": 1},
    {"q": "What is the unit of force in SI?", "type": "mc", "opts": ["Joule", "Newton", "Watt", "Pascal"], "ans": "Newton", "exp": "The Newton (N) is the SI unit of force, equal to kg⋅m/s².", "cat": "mechanics", "diff": 1},
    {"q": "Kinetic energy formula is KE = ?", "type": "mc", "opts": ["mv", "½mv²", "mgh", "½mv"], "ans": "½mv²", "exp": "Kinetic energy is half the mass times velocity squared.", "cat": "mechanics", "diff": 1},
    {"q": "Potential energy due to gravity is PE = ?", "type": "mc", "opts": ["mgh", "½mv²", "Fd", "½kx²"], "ans": "mgh", "exp": "Gravitational potential energy equals mass × gravity × height.", "cat": "mechanics", "diff": 1},
    {"q": "What is momentum equal to?", "type": "mc", "opts": ["m × v", "m × a", "F × t", "m × g"], "ans": "m × v", "exp": "Momentum (p) is mass times velocity.", "cat": "mechanics", "diff": 1},
    {"q": "In an elastic collision, what is conserved?", "type": "mc", "opts": ["Only momentum", "Only kinetic energy", "Both momentum and kinetic energy", "Neither"], "ans": "Both momentum and kinetic energy", "exp": "Elastic collisions conserve both momentum and kinetic energy.", "cat": "mechanics", "diff": 2},
    {"q": "What is the acceleration due to gravity on Earth?", "type": "mc", "opts": ["9.8 m/s", "9.8 m/s²", "10 m/s²", "8.9 m/s²"], "ans": "9.8 m/s²", "exp": "Standard gravity is approximately 9.8 meters per second squared.", "cat": "mechanics", "diff": 1},
    {"q": "Angular velocity is measured in?", "type": "mc", "opts": ["m/s", "rad/s", "degrees", "rpm only"], "ans": "rad/s", "exp": "Angular velocity in SI units is radians per second.", "cat": "mechanics", "diff": 2},
    {"q": "Torque equals?", "type": "mc", "opts": ["F × r", "F / r", "F + r", "F × r²"], "ans": "F × r", "exp": "Torque is force times the perpendicular distance (lever arm).", "cat": "mechanics", "diff": 2},
    {"q": "What is the moment of inertia for a solid sphere?", "type": "mc", "opts": ["⅖mr²", "½mr²", "mr²", "⅔mr²"], "ans": "⅖mr²", "exp": "A solid sphere has moment of inertia (2/5)mr² about its center.", "cat": "mechanics", "diff": 3},
    {"q": "Centripetal acceleration formula is?", "type": "mc", "opts": ["v²/r", "vr", "v/r", "r/v²"], "ans": "v²/r", "exp": "Centripetal acceleration equals velocity squared divided by radius.", "cat": "mechanics", "diff": 2},
    {"q": "Work done equals?", "type": "mc", "opts": ["F × d × cos(θ)", "F × d × sin(θ)", "F / d", "F + d"], "ans": "F × d × cos(θ)", "exp": "Work is force times displacement times cosine of the angle between them.", "cat": "mechanics", "diff": 2},
    {"q": "Power is defined as?", "type": "mc", "opts": ["Work / Time", "Force × Time", "Energy × Time", "Work × Time"], "ans": "Work / Time", "exp": "Power is the rate of doing work, measured in Watts.", "cat": "mechanics", "diff": 1},
    {"q": "Impulse equals change in?", "type": "mc", "opts": ["Velocity", "Momentum", "Energy", "Force"], "ans": "Momentum", "exp": "Impulse (F×t) equals the change in momentum.", "cat": "mechanics", "diff": 2},
    {"q": "What type of friction acts on a moving object?", "type": "mc", "opts": ["Static", "Kinetic", "Rolling", "Fluid"], "ans": "Kinetic", "exp": "Kinetic friction acts on objects that are already in motion.", "cat": "mechanics", "diff": 1},
    {"q": "The coefficient of friction is?", "type": "mc", "opts": ["Always > 1", "Always < 1", "Dimensionless ratio", "Measured in Newtons"], "ans": "Dimensionless ratio", "exp": "Coefficient of friction is a dimensionless ratio, typically between 0 and 1 but can exceed 1.", "cat": "mechanics", "diff": 2},
    {"q": "Terminal velocity occurs when?", "type": "mc", "opts": ["Drag equals weight", "Acceleration is maximum", "Object stops", "Gravity is zero"], "ans": "Drag equals weight", "exp": "Terminal velocity is reached when air resistance equals gravitational force.", "cat": "mechanics", "diff": 2},
    {"q": "Hooke's Law states F = ?", "type": "mc", "opts": ["-kx", "kx²", "k/x", "mx"], "ans": "-kx", "exp": "Hooke's Law: Spring force equals negative spring constant times displacement.", "cat": "mechanics", "diff": 2},
    {"q": "Simple harmonic motion period T = ?", "type": "mc", "opts": ["2π√(m/k)", "2π√(k/m)", "π√(m/k)", "2π(m/k)"], "ans": "2π√(m/k)", "exp": "Period of a mass-spring system is 2π times square root of mass over spring constant.", "cat": "mechanics", "diff": 3},
    
    # Game Physics (25)
    {"q": "What integration method is simplest but least accurate?", "type": "mc", "opts": ["Euler", "Verlet", "RK4", "Midpoint"], "ans": "Euler", "exp": "Euler integration is simplest but accumulates error quickly.", "cat": "game_physics", "diff": 2},
    {"q": "Verlet integration is preferred for?", "type": "mc", "opts": ["Cloth simulation", "Projectiles", "Sound", "UI animation"], "ans": "Cloth simulation", "exp": "Verlet integration is stable and position-based, ideal for constraints like cloth.", "cat": "game_physics", "diff": 2},
    {"q": "What does a physics timestep (dt) represent?", "type": "mc", "opts": ["Time between frames", "Fixed simulation step", "Total game time", "Render time"], "ans": "Fixed simulation step", "exp": "dt is typically a fixed timestep for deterministic physics simulation.", "cat": "game_physics", "diff": 2},
    {"q": "Why use fixed timestep physics?", "type": "mc", "opts": ["Faster rendering", "Deterministic results", "Less memory", "Better graphics"], "ans": "Deterministic results", "exp": "Fixed timestep ensures consistent physics regardless of framerate.", "cat": "game_physics", "diff": 2},
    {"q": "Broad phase collision detection uses?", "type": "mc", "opts": ["AABBs and spatial hashing", "Exact geometry", "Pixel-perfect checks", "Ray marching"], "ans": "AABBs and spatial hashing", "exp": "Broad phase quickly eliminates non-colliding pairs using simple bounds.", "cat": "game_physics", "diff": 3},
    {"q": "Narrow phase collision detection does?", "type": "mc", "opts": ["Eliminates pairs", "Exact intersection tests", "Spatial partitioning", "Bounding volumes"], "ans": "Exact intersection tests", "exp": "Narrow phase performs precise collision tests on candidate pairs.", "cat": "game_physics", "diff": 3},
    {"q": "GJK algorithm is used for?", "type": "mc", "opts": ["Convex collision detection", "Pathfinding", "Rendering", "Audio"], "ans": "Convex collision detection", "exp": "Gilbert-Johnson-Keerthi detects collision between convex shapes.", "cat": "game_physics", "diff": 4},
    {"q": "SAT stands for?", "type": "mc", "opts": ["Separating Axis Theorem", "Spatial Acceleration Tree", "Simple Axis Test", "Surface Area Test"], "ans": "Separating Axis Theorem", "exp": "SAT tests for separating axes between convex polygons.", "cat": "game_physics", "diff": 3},
    {"q": "What is a manifold in collision?", "type": "mc", "opts": ["Contact points and normals", "A 3D mesh", "Physics material", "Bounding box"], "ans": "Contact points and normals", "exp": "A collision manifold contains contact points and surface normals.", "cat": "game_physics", "diff": 3},
    {"q": "Restitution coefficient of 1 means?", "type": "mc", "opts": ["Perfectly elastic", "Perfectly inelastic", "No bounce", "Infinite bounce"], "ans": "Perfectly elastic", "exp": "Restitution of 1 means all kinetic energy is preserved (perfect bounce).", "cat": "game_physics", "diff": 2},
    {"q": "Restitution of 0 means?", "type": "mc", "opts": ["Maximum bounce", "No bounce", "Infinite energy", "Objects pass through"], "ans": "No bounce", "exp": "Zero restitution means a completely inelastic collision with no bounce.", "cat": "game_physics", "diff": 2},
    {"q": "What is a constraint solver?", "type": "mc", "opts": ["Resolves physical constraints iteratively", "Solves AI behavior", "Renders constraints", "Loads assets"], "ans": "Resolves physical constraints iteratively", "exp": "Constraint solvers iteratively satisfy joints, contacts, and limits.", "cat": "game_physics", "diff": 3},
    {"q": "Sequential Impulse is used for?", "type": "mc", "opts": ["Constraint solving", "Rendering", "Audio mixing", "Networking"], "ans": "Constraint solving", "exp": "Sequential Impulse iteratively applies corrective impulses to constraints.", "cat": "game_physics", "diff": 4},
    {"q": "What is CCD in physics?", "type": "mc", "opts": ["Continuous Collision Detection", "Central Core Data", "Collision Count Display", "Contact Compute Device"], "ans": "Continuous Collision Detection", "exp": "CCD prevents fast objects from tunneling through thin objects.", "cat": "game_physics", "diff": 3},
    {"q": "Tunneling in physics means?", "type": "mc", "opts": ["Objects passing through each other", "Underground movement", "Network latency", "Memory leak"], "ans": "Objects passing through each other", "exp": "Tunneling occurs when fast objects skip past collision geometry between frames.", "cat": "game_physics", "diff": 2},
    {"q": "A ragdoll uses?", "type": "mc", "opts": ["Rigid bodies with joints", "Single rigid body", "Soft body only", "Static mesh"], "ans": "Rigid bodies with joints", "exp": "Ragdolls are hierarchies of rigid bodies connected by constrained joints.", "cat": "game_physics", "diff": 2},
    {"q": "Inverse Kinematics (IK) solves for?", "type": "mc", "opts": ["Joint angles from end position", "End position from angles", "Collision response", "Fluid flow"], "ans": "Joint angles from end position", "exp": "IK calculates joint rotations needed to reach a target position.", "cat": "game_physics", "diff": 3},
    {"q": "Forward Kinematics calculates?", "type": "mc", "opts": ["End position from joint angles", "Joint angles from position", "Collision detection", "Physics timestep"], "ans": "End position from joint angles", "exp": "FK computes final positions by applying joint transforms in order.", "cat": "game_physics", "diff": 3},
    {"q": "What is a physics material?", "type": "mc", "opts": ["Friction and restitution properties", "Texture data", "Shader program", "Audio clip"], "ans": "Friction and restitution properties", "exp": "Physics materials define surface properties like friction and bounciness.", "cat": "game_physics", "diff": 2},
    {"q": "Sleep state in physics means?", "type": "mc", "opts": ["Object is not simulated until disturbed", "Game is paused", "Object is deleted", "Low framerate"], "ans": "Object is not simulated until disturbed", "exp": "Sleeping objects are skipped in simulation until awakened by collision or force.", "cat": "game_physics", "diff": 2},
    {"q": "Why is physics interpolation used?", "type": "mc", "opts": ["Smooth rendering between fixed steps", "Faster simulation", "Less memory", "Better collisions"], "ans": "Smooth rendering between fixed steps", "exp": "Interpolation smooths visual movement between discrete physics updates.", "cat": "game_physics", "diff": 3},
    {"q": "Substeps in physics increase?", "type": "mc", "opts": ["Accuracy at cost of performance", "Performance", "Memory usage only", "Rendering quality"], "ans": "Accuracy at cost of performance", "exp": "More substeps improve simulation accuracy but require more CPU time.", "cat": "game_physics", "diff": 3},
    {"q": "An AABB is?", "type": "mc", "opts": ["Axis-Aligned Bounding Box", "Automatic Animation Blend", "Audio Amplitude Buffer", "Asset Assembly Build"], "ans": "Axis-Aligned Bounding Box", "exp": "AABB is a simple rectangular volume aligned to world axes.", "cat": "game_physics", "diff": 2},
    {"q": "OBB stands for?", "type": "mc", "opts": ["Oriented Bounding Box", "Offset Blend Buffer", "Optimal Binary Branch", "Object Behavior Base"], "ans": "Oriented Bounding Box", "exp": "OBB is a bounding box that rotates with the object.", "cat": "game_physics", "diff": 2},
    {"q": "A convex hull is?", "type": "mc", "opts": ["Smallest convex shape containing all points", "Concave mesh", "Texture mapping", "Audio waveform"], "ans": "Smallest convex shape containing all points", "exp": "Convex hull is like shrink-wrapping a rubber band around points.", "cat": "game_physics", "diff": 3},
    
    # Fluids & Particles (15)
    {"q": "SPH stands for?", "type": "mc", "opts": ["Smoothed Particle Hydrodynamics", "Simple Physics Handler", "Spatial Partition Hash", "System Process Hook"], "ans": "Smoothed Particle Hydrodynamics", "exp": "SPH simulates fluids using particles with smoothing kernels.", "cat": "fluids", "diff": 3},
    {"q": "Navier-Stokes equations describe?", "type": "mc", "opts": ["Fluid motion", "Rigid body dynamics", "Electromagnetic waves", "Heat transfer only"], "ans": "Fluid motion", "exp": "Navier-Stokes equations govern viscous fluid flow.", "cat": "fluids", "diff": 3},
    {"q": "Eulerian fluid simulation uses?", "type": "mc", "opts": ["Fixed grid", "Moving particles", "Hybrid approach", "No grid"], "ans": "Fixed grid", "exp": "Eulerian methods simulate fluid properties on a fixed spatial grid.", "cat": "fluids", "diff": 3},
    {"q": "Lagrangian fluid simulation uses?", "type": "mc", "opts": ["Moving particles", "Fixed grid", "Static mesh", "Voxels only"], "ans": "Moving particles", "exp": "Lagrangian methods track individual fluid particles.", "cat": "fluids", "diff": 3},
    {"q": "FLIP stands for?", "type": "mc", "opts": ["Fluid Implicit Particle", "Fast Linear Interpolation", "Fixed Length Integer Pack", "Frame Layer Index Pointer"], "ans": "Fluid Implicit Particle", "exp": "FLIP combines Eulerian grids with Lagrangian particles.", "cat": "fluids", "diff": 4},
    {"q": "Viscosity in fluids causes?", "type": "mc", "opts": ["Resistance to flow", "Faster flow", "Color change", "Temperature increase"], "ans": "Resistance to flow", "exp": "Viscosity is internal friction that resists fluid deformation.", "cat": "fluids", "diff": 2},
    {"q": "Surface tension causes?", "type": "mc", "opts": ["Liquid to minimize surface area", "Evaporation", "Freezing", "Color mixing"], "ans": "Liquid to minimize surface area", "exp": "Surface tension makes liquids form droplets and spheres.", "cat": "fluids", "diff": 2},
    {"q": "Buoyancy force depends on?", "type": "mc", "opts": ["Displaced fluid volume", "Object color", "Time of day", "Air temperature"], "ans": "Displaced fluid volume", "exp": "Archimedes' principle: buoyancy equals weight of displaced fluid.", "cat": "fluids", "diff": 2},
    {"q": "Particle emitters create?", "type": "mc", "opts": ["New particles over time", "Rigid bodies", "Textures", "Sound waves"], "ans": "New particles over time", "exp": "Emitters spawn particles with initial properties like velocity and color.", "cat": "fluids", "diff": 1},
    {"q": "Particle lifetime determines?", "type": "mc", "opts": ["How long particle exists", "Particle color", "Spawn rate", "Texture resolution"], "ans": "How long particle exists", "exp": "Lifetime controls when particles are removed from simulation.", "cat": "fluids", "diff": 1},
    {"q": "Billboarding in particles means?", "type": "mc", "opts": ["Sprites always face camera", "3D rendering", "Particle collision", "LOD switching"], "ans": "Sprites always face camera", "exp": "Billboard particles rotate to always face the viewer.", "cat": "fluids", "diff": 2},
    {"q": "GPU particle systems advantage?", "type": "mc", "opts": ["Millions of particles", "Better physics accuracy", "Simpler code", "Less memory"], "ans": "Millions of particles", "exp": "GPUs can simulate and render millions of particles in parallel.", "cat": "fluids", "diff": 2},
    {"q": "Curl noise is used for?", "type": "mc", "opts": ["Turbulent fluid motion", "Audio synthesis", "Encryption", "Pathfinding"], "ans": "Turbulent fluid motion", "exp": "Curl noise creates divergence-free velocity fields for realistic turbulence.", "cat": "fluids", "diff": 3},
    {"q": "Reynolds number indicates?", "type": "mc", "opts": ["Laminar vs turbulent flow", "Fluid color", "Temperature", "Density only"], "ans": "Laminar vs turbulent flow", "exp": "High Reynolds number indicates turbulent flow, low indicates laminar.", "cat": "fluids", "diff": 3},
    {"q": "Position Based Dynamics (PBD) is good for?", "type": "mc", "opts": ["Real-time soft bodies and cloth", "Offline rendering", "Audio processing", "Network sync"], "ans": "Real-time soft bodies and cloth", "exp": "PBD provides stable, real-time simulation of deformable objects.", "cat": "fluids", "diff": 3},
    
    # Soft Bodies & Cloth (15)
    {"q": "Mass-spring systems model cloth using?", "type": "mc", "opts": ["Particles connected by springs", "Single rigid mesh", "Fluid simulation", "Ray tracing"], "ans": "Particles connected by springs", "exp": "Cloth is simulated as a grid of masses connected by spring constraints.", "cat": "soft_body", "diff": 2},
    {"q": "Structural springs in cloth resist?", "type": "mc", "opts": ["Stretching", "Bending", "Shearing", "Tearing"], "ans": "Stretching", "exp": "Structural springs connect adjacent particles and resist stretching.", "cat": "soft_body", "diff": 2},
    {"q": "Shear springs in cloth connect?", "type": "mc", "opts": ["Diagonal neighbors", "Direct neighbors", "Every other particle", "Random particles"], "ans": "Diagonal neighbors", "exp": "Shear springs connect diagonally to resist shearing deformation.", "cat": "soft_body", "diff": 2},
    {"q": "Bend springs connect?", "type": "mc", "opts": ["Particles two steps apart", "Adjacent particles", "Diagonal only", "Random pairs"], "ans": "Particles two steps apart", "exp": "Bend springs skip one particle to resist bending.", "cat": "soft_body", "diff": 2},
    {"q": "Cloth self-collision prevents?", "type": "mc", "opts": ["Cloth passing through itself", "Wind effects", "Stretching", "Color bleeding"], "ans": "Cloth passing through itself", "exp": "Self-collision detection stops cloth from interpenetrating.", "cat": "soft_body", "diff": 2},
    {"q": "Damping in cloth simulation?", "type": "mc", "opts": ["Reduces oscillation", "Increases speed", "Adds color", "Improves texture"], "ans": "Reduces oscillation", "exp": "Damping dissipates energy to prevent unrealistic oscillation.", "cat": "soft_body", "diff": 2},
    {"q": "Wind force on cloth depends on?", "type": "mc", "opts": ["Surface normal and velocity", "Particle color", "Spring stiffness", "Texture resolution"], "ans": "Surface normal and velocity", "exp": "Wind force considers the angle and relative velocity of air hitting cloth.", "cat": "soft_body", "diff": 3},
    {"q": "Finite Element Method (FEM) is used for?", "type": "mc", "opts": ["Accurate deformable solids", "Particle effects", "Rigid bodies only", "Audio synthesis"], "ans": "Accurate deformable solids", "exp": "FEM provides physically accurate soft body simulation using mesh elements.", "cat": "soft_body", "diff": 4},
    {"q": "Tetrahedral meshes in soft bodies?", "type": "mc", "opts": ["Allow volumetric deformation", "Only surface deformation", "Faster than triangles", "For 2D only"], "ans": "Allow volumetric deformation", "exp": "Tetrahedra fill the volume allowing internal stress simulation.", "cat": "soft_body", "diff": 3},
    {"q": "Shape matching in PBD?", "type": "mc", "opts": ["Pulls particles toward rest shape", "Matches textures", "Collision detection", "Audio matching"], "ans": "Pulls particles toward rest shape", "exp": "Shape matching computes optimal rigid transform and pulls particles toward it.", "cat": "soft_body", "diff": 3},
    {"q": "Strain limiting prevents?", "type": "mc", "opts": ["Excessive stretching", "Collision", "Wind effects", "Rendering errors"], "ans": "Excessive stretching", "exp": "Strain limiting clamps deformation to prevent unrealistic stretching.", "cat": "soft_body", "diff": 3},
    {"q": "Pressure force in soft bodies?", "type": "mc", "opts": ["Maintains internal volume", "Causes stretching", "Adds friction", "Changes color"], "ans": "Maintains internal volume", "exp": "Pressure constraints keep inflated objects from collapsing.", "cat": "soft_body", "diff": 3},
    {"q": "Plasticity in soft bodies means?", "type": "mc", "opts": ["Permanent deformation", "Elastic return", "No deformation", "Faster simulation"], "ans": "Permanent deformation", "exp": "Plastic deformation doesn't spring back to original shape.", "cat": "soft_body", "diff": 3},
    {"q": "Long Range Attachments in cloth?", "type": "mc", "opts": ["Prevent super-elastic behavior", "Add more springs", "Improve rendering", "Handle tearing"], "ans": "Prevent super-elastic behavior", "exp": "LRA constraints prevent cloth from stretching too much under gravity.", "cat": "soft_body", "diff": 4},
    {"q": "Cloth LOD reduces?", "type": "mc", "opts": ["Particle count at distance", "Texture quality", "Physics accuracy only", "Audio quality"], "ans": "Particle count at distance", "exp": "Level of Detail reduces cloth complexity for distant objects.", "cat": "soft_body", "diff": 2},
    
    # Constraints & Joints (20)
    {"q": "A hinge joint allows?", "type": "mc", "opts": ["Rotation around one axis", "All rotations", "No movement", "Translation only"], "ans": "Rotation around one axis", "exp": "Hinge joints rotate around a single axis like a door.", "cat": "constraints", "diff": 1},
    {"q": "A ball-and-socket joint allows?", "type": "mc", "opts": ["Rotation around all axes", "One axis rotation", "Translation only", "No movement"], "ans": "Rotation around all axes", "exp": "Ball joints allow rotation in any direction like a shoulder.", "cat": "constraints", "diff": 1},
    {"q": "A slider/prismatic joint allows?", "type": "mc", "opts": ["Linear translation along one axis", "All rotations", "No movement", "Rotation only"], "ans": "Linear translation along one axis", "exp": "Prismatic joints slide along a single axis.", "cat": "constraints", "diff": 2},
    {"q": "A fixed joint does?", "type": "mc", "opts": ["Locks all degrees of freedom", "Allows all movement", "Only rotation", "Only translation"], "ans": "Locks all degrees of freedom", "exp": "Fixed joints rigidly attach two bodies together.", "cat": "constraints", "diff": 1},
    {"q": "Distance constraint maintains?", "type": "mc", "opts": ["Fixed distance between points", "Fixed angle", "Fixed velocity", "Fixed color"], "ans": "Fixed distance between points", "exp": "Distance constraints keep two points at a specific separation.", "cat": "constraints", "diff": 2},
    {"q": "Joint limits restrict?", "type": "mc", "opts": ["Range of motion", "Joint color", "Rendering quality", "Audio volume"], "ans": "Range of motion", "exp": "Limits define minimum and maximum allowed joint angles or positions.", "cat": "constraints", "diff": 2},
    {"q": "Joint motors provide?", "type": "mc", "opts": ["Powered movement at joints", "Visual effects", "Sound", "Collision"], "ans": "Powered movement at joints", "exp": "Motors apply torque or force to drive joints to target positions.", "cat": "constraints", "diff": 2},
    {"q": "Break force on joints means?", "type": "mc", "opts": ["Force that destroys the joint", "Joint strength", "Starting force", "Rendering force"], "ans": "Force that destroys the joint", "exp": "Joints can break when forces exceed the break threshold.", "cat": "constraints", "diff": 2},
    {"q": "DOF in joints stands for?", "type": "mc", "opts": ["Degrees of Freedom", "Direction of Force", "Data Output Format", "Dynamic Object Flag"], "ans": "Degrees of Freedom", "exp": "DOF indicates how many independent motions a joint allows.", "cat": "constraints", "diff": 1},
    {"q": "A 6-DOF joint allows?", "type": "mc", "opts": ["All translation and rotation", "Only rotation", "Only translation", "No movement"], "ans": "All translation and rotation", "exp": "Six DOF means 3 translation and 3 rotation axes are free.", "cat": "constraints", "diff": 2},
    {"q": "Constraint solver iterations affect?", "type": "mc", "opts": ["Stiffness and accuracy", "Visual quality", "Audio quality", "Network latency"], "ans": "Stiffness and accuracy", "exp": "More iterations make constraints stiffer and more accurate.", "cat": "constraints", "diff": 3},
    {"q": "Warm starting constraints means?", "type": "mc", "opts": ["Using previous frame's solution", "Heating physics objects", "First frame setup", "Slow initialization"], "ans": "Using previous frame's solution", "exp": "Warm starting reuses previous impulses for faster convergence.", "cat": "constraints", "diff": 3},
    {"q": "Baumgarte stabilization?", "type": "mc", "opts": ["Corrects constraint drift", "Improves rendering", "Handles audio", "Network sync"], "ans": "Corrects constraint drift", "exp": "Baumgarte adds a correction term to fix accumulated constraint errors.", "cat": "constraints", "diff": 4},
    {"q": "A rope/chain uses?", "type": "mc", "opts": ["Series of distance constraints", "Single rigid body", "Fluid simulation", "Soft body only"], "ans": "Series of distance constraints", "exp": "Ropes are chains of particles connected by distance constraints.", "cat": "constraints", "diff": 2},
    {"q": "Contact constraint prevents?", "type": "mc", "opts": ["Penetration between bodies", "Separation", "Rotation", "Friction"], "ans": "Penetration between bodies", "exp": "Contact constraints push colliding bodies apart.", "cat": "constraints", "diff": 2},
    {"q": "Friction constraint provides?", "type": "mc", "opts": ["Tangential resistance at contacts", "Normal force", "Separation force", "Rotation only"], "ans": "Tangential resistance at contacts", "exp": "Friction constraints resist sliding at contact points.", "cat": "constraints", "diff": 3},
    {"q": "Island in physics simulation?", "type": "mc", "opts": ["Group of interacting bodies", "Water feature", "Rendering group", "Audio zone"], "ans": "Group of interacting bodies", "exp": "Islands are clusters of bodies connected by contacts or joints, solved together.", "cat": "constraints", "diff": 3},
    {"q": "Constraint softness allows?", "type": "mc", "opts": ["Some violation for stability", "Harder constraints", "Better visuals", "Faster solving"], "ans": "Some violation for stability", "exp": "Soft constraints are slightly elastic, improving stability.", "cat": "constraints", "diff": 3},
    {"q": "A cone twist joint is?", "type": "mc", "opts": ["Ball joint with cone limits", "Hinge joint", "Slider joint", "Fixed joint"], "ans": "Ball joint with cone limits", "exp": "Cone twist allows rotation within a cone-shaped limit.", "cat": "constraints", "diff": 3},
    {"q": "Spring joint adds?", "type": "mc", "opts": ["Elastic connection between bodies", "Rigid connection", "No connection", "Only collision"], "ans": "Elastic connection between bodies", "exp": "Spring joints pull bodies together like connected by a spring.", "cat": "constraints", "diff": 2},
]

# ============================================================================
# MATH QUIZ BANK - 95 Questions
# ============================================================================

MATH_QUIZZES = [
    # Linear Algebra (30)
    {"q": "A vector has both?", "type": "mc", "opts": ["Magnitude and direction", "Only magnitude", "Only direction", "Color and size"], "ans": "Magnitude and direction", "exp": "Vectors represent quantities with both size and direction.", "cat": "linear_algebra", "diff": 1},
    {"q": "Dot product of perpendicular vectors is?", "type": "mc", "opts": ["0", "1", "-1", "Infinity"], "ans": "0", "exp": "Perpendicular vectors have 90° angle, cos(90°) = 0.", "cat": "linear_algebra", "diff": 1},
    {"q": "Cross product produces?", "type": "mc", "opts": ["A vector perpendicular to both inputs", "A scalar", "Same direction vector", "Zero always"], "ans": "A vector perpendicular to both inputs", "exp": "Cross product yields a vector orthogonal to both input vectors.", "cat": "linear_algebra", "diff": 2},
    {"q": "Unit vector has magnitude?", "type": "mc", "opts": ["1", "0", "Any value", "Depends on dimension"], "ans": "1", "exp": "Unit vectors are normalized to have length 1.", "cat": "linear_algebra", "diff": 1},
    {"q": "To normalize a vector, divide by?", "type": "mc", "opts": ["Its magnitude", "2", "Its x component", "Zero"], "ans": "Its magnitude", "exp": "Normalization divides each component by the vector's length.", "cat": "linear_algebra", "diff": 1},
    {"q": "Matrix multiplication is?", "type": "mc", "opts": ["Not commutative (AB ≠ BA)", "Always commutative", "Undefined", "Only for square matrices"], "ans": "Not commutative (AB ≠ BA)", "exp": "Matrix multiplication order matters; AB usually ≠ BA.", "cat": "linear_algebra", "diff": 2},
    {"q": "Identity matrix multiplied by A gives?", "type": "mc", "opts": ["A", "Zero matrix", "Transpose of A", "Inverse of A"], "ans": "A", "exp": "Identity matrix is the multiplicative identity: IA = A.", "cat": "linear_algebra", "diff": 1},
    {"q": "Determinant of 2x2 matrix [[a,b],[c,d]] is?", "type": "mc", "opts": ["ad - bc", "ad + bc", "ab - cd", "ac - bd"], "ans": "ad - bc", "exp": "2x2 determinant is product of diagonal minus product of anti-diagonal.", "cat": "linear_algebra", "diff": 2},
    {"q": "If determinant is 0, matrix is?", "type": "mc", "opts": ["Singular/non-invertible", "Identity", "Orthogonal", "Symmetric"], "ans": "Singular/non-invertible", "exp": "Zero determinant means the matrix has no inverse.", "cat": "linear_algebra", "diff": 2},
    {"q": "Transpose of matrix A swaps?", "type": "mc", "opts": ["Rows and columns", "Diagonal elements", "Signs", "Nothing"], "ans": "Rows and columns", "exp": "Transpose reflects the matrix over its main diagonal.", "cat": "linear_algebra", "diff": 1},
    {"q": "Orthogonal matrix has property?", "type": "mc", "opts": ["Inverse equals transpose", "All zeros", "Determinant 0", "Not invertible"], "ans": "Inverse equals transpose", "exp": "Orthogonal matrices satisfy A⁻¹ = Aᵀ.", "cat": "linear_algebra", "diff": 2},
    {"q": "Rotation matrices are?", "type": "mc", "opts": ["Orthogonal with determinant 1", "Singular", "Not orthogonal", "Always 2x2"], "ans": "Orthogonal with determinant 1", "exp": "Pure rotation matrices are orthogonal with det = +1.", "cat": "linear_algebra", "diff": 2},
    {"q": "Eigenvalue equation is?", "type": "mc", "opts": ["Av = λv", "A + v = λ", "Av = v", "A = λ"], "ans": "Av = λv", "exp": "Eigenvalues λ scale eigenvectors v when multiplied by A.", "cat": "linear_algebra", "diff": 3},
    {"q": "Homogeneous coordinates add?", "type": "mc", "opts": ["An extra dimension (w)", "Color", "Nothing", "Time"], "ans": "An extra dimension (w)", "exp": "Homogeneous coords add w component for unified transformations.", "cat": "linear_algebra", "diff": 2},
    {"q": "Translation in matrix form requires?", "type": "mc", "opts": ["4x4 matrix (homogeneous)", "3x3 matrix", "2x2 matrix", "No matrix needed"], "ans": "4x4 matrix (homogeneous)", "exp": "Translation needs 4x4 matrices with homogeneous coordinates.", "cat": "linear_algebra", "diff": 2},
    {"q": "Model matrix transforms from?", "type": "mc", "opts": ["Local to world space", "World to view space", "View to clip space", "Clip to screen"], "ans": "Local to world space", "exp": "Model matrix positions objects in the world.", "cat": "linear_algebra", "diff": 2},
    {"q": "View matrix transforms from?", "type": "mc", "opts": ["World to camera space", "Local to world", "Clip to screen", "UV to texture"], "ans": "World to camera space", "exp": "View matrix moves world relative to camera position.", "cat": "linear_algebra", "diff": 2},
    {"q": "Projection matrix transforms from?", "type": "mc", "opts": ["View to clip space", "Local to world", "World to view", "Screen to pixel"], "ans": "View to clip space", "exp": "Projection matrix applies perspective or orthographic projection.", "cat": "linear_algebra", "diff": 2},
    {"q": "MVP matrix order is?", "type": "mc", "opts": ["Projection × View × Model", "Model × View × Projection", "View × Model × Projection", "Any order"], "ans": "Projection × View × Model", "exp": "Transformations apply right-to-left: model first, then view, then projection.", "cat": "linear_algebra", "diff": 3},
    {"q": "Scaling matrix has values on?", "type": "mc", "opts": ["Diagonal", "Last row", "First column", "Random positions"], "ans": "Diagonal", "exp": "Scale factors appear on the main diagonal of the matrix.", "cat": "linear_algebra", "diff": 2},
    {"q": "Reflection matrix has determinant?", "type": "mc", "opts": ["-1", "1", "0", "2"], "ans": "-1", "exp": "Reflection flips handedness, giving determinant of -1.", "cat": "linear_algebra", "diff": 3},
    {"q": "Shear transformation affects?", "type": "mc", "opts": ["One axis based on another", "All axes equally", "Only rotation", "Only translation"], "ans": "One axis based on another", "exp": "Shearing skews one axis proportionally to position on another.", "cat": "linear_algebra", "diff": 2},
    {"q": "Affine transformation preserves?", "type": "mc", "opts": ["Parallel lines", "Distances", "Angles", "All shapes"], "ans": "Parallel lines", "exp": "Affine transforms preserve parallelism and ratios along lines.", "cat": "linear_algebra", "diff": 3},
    {"q": "Linear interpolation formula?", "type": "mc", "opts": ["a + (b-a)t", "a × b × t", "(a + b) / t", "a - b + t"], "ans": "a + (b-a)t", "exp": "Lerp blends from a to b based on parameter t.", "cat": "linear_algebra", "diff": 1},
    {"q": "Bilinear interpolation uses?", "type": "mc", "opts": ["4 values in 2D", "2 values", "8 values", "1 value"], "ans": "4 values in 2D", "exp": "Bilinear interpolates between 4 corners in a 2D grid.", "cat": "linear_algebra", "diff": 2},
    {"q": "Barycentric coordinates sum to?", "type": "mc", "opts": ["1", "0", "3", "Depends on triangle"], "ans": "1", "exp": "Barycentric weights for a point inside a triangle sum to 1.", "cat": "linear_algebra", "diff": 3},
    {"q": "Negative barycentric coordinate means?", "type": "mc", "opts": ["Point outside triangle", "Inside triangle", "On edge", "At vertex"], "ans": "Point outside triangle", "exp": "Negative weights indicate the point is outside the triangle.", "cat": "linear_algebra", "diff": 3},
    {"q": "Gram-Schmidt process creates?", "type": "mc", "opts": ["Orthonormal basis", "Inverse matrix", "Eigenvalues", "Determinant"], "ans": "Orthonormal basis", "exp": "Gram-Schmidt orthonormalizes a set of vectors.", "cat": "linear_algebra", "diff": 3},
    {"q": "LU decomposition factors matrix into?", "type": "mc", "opts": ["Lower and Upper triangular", "Left and Up", "Linear and Unitary", "Large and Uniform"], "ans": "Lower and Upper triangular", "exp": "LU breaks a matrix into lower and upper triangular factors.", "cat": "linear_algebra", "diff": 4},
    {"q": "SVD stands for?", "type": "mc", "opts": ["Singular Value Decomposition", "Simple Vector Direction", "Standard Variance Distribution", "Scaled Vector Division"], "ans": "Singular Value Decomposition", "exp": "SVD factors any matrix into U·Σ·Vᵀ.", "cat": "linear_algebra", "diff": 4},
    
    # Trigonometry & Geometry (25)
    {"q": "π radians equals?", "type": "mc", "opts": ["180°", "90°", "360°", "45°"], "ans": "180°", "exp": "π radians = 180 degrees, a half circle.", "cat": "geometry", "diff": 1},
    {"q": "sin²θ + cos²θ = ?", "type": "mc", "opts": ["1", "0", "2", "θ"], "ans": "1", "exp": "Pythagorean identity: sine squared plus cosine squared equals 1.", "cat": "geometry", "diff": 1},
    {"q": "atan2(y, x) gives?", "type": "mc", "opts": ["Angle in all 4 quadrants", "Only positive angles", "Only first quadrant", "Undefined for negative"], "ans": "Angle in all 4 quadrants", "exp": "atan2 handles all quadrants correctly, unlike regular atan.", "cat": "geometry", "diff": 2},
    {"q": "Distance formula in 2D?", "type": "mc", "opts": ["√((x₂-x₁)² + (y₂-y₁)²)", "(x₂-x₁) + (y₂-y₁)", "|x₂-x₁| × |y₂-y₁|", "(x₂+x₁) / 2"], "ans": "√((x₂-x₁)² + (y₂-y₁)²)", "exp": "Euclidean distance uses the Pythagorean theorem.", "cat": "geometry", "diff": 1},
    {"q": "Midpoint formula?", "type": "mc", "opts": ["((x₁+x₂)/2, (y₁+y₂)/2)", "(x₁×x₂, y₁×y₂)", "(x₂-x₁, y₂-y₁)", "(x₁, y₂)"], "ans": "((x₁+x₂)/2, (y₁+y₂)/2)", "exp": "Midpoint averages the coordinates.", "cat": "geometry", "diff": 1},
    {"q": "Normal vector is?", "type": "mc", "opts": ["Perpendicular to surface", "Parallel to surface", "Random direction", "Always up"], "ans": "Perpendicular to surface", "exp": "Normal vectors point perpendicular to their surface.", "cat": "geometry", "diff": 1},
    {"q": "Plane equation Ax + By + Cz + D = 0, (A,B,C) is?", "type": "mc", "opts": ["Normal vector", "Point on plane", "Tangent", "Center"], "ans": "Normal vector", "exp": "Coefficients (A, B, C) form the plane's normal vector.", "cat": "geometry", "diff": 2},
    {"q": "Point-to-plane distance uses?", "type": "mc", "opts": ["Dot product with normal", "Cross product", "Subtraction only", "Division"], "ans": "Dot product with normal", "exp": "Distance = |Ax + By + Cz + D| / ||(A,B,C)||", "cat": "geometry", "diff": 3},
    {"q": "Ray-plane intersection tests?", "type": "mc", "opts": ["When ray crosses plane", "Parallel alignment", "Color matching", "Sound collision"], "ans": "When ray crosses plane", "exp": "Ray-plane intersection finds where a ray penetrates a plane.", "cat": "geometry", "diff": 2},
    {"q": "Sphere equation (x-a)² + (y-b)² + (z-c)² = ?", "type": "mc", "opts": ["r²", "r", "2r", "πr²"], "ans": "r²", "exp": "Points on sphere are distance r from center (a,b,c).", "cat": "geometry", "diff": 2},
    {"q": "Ray-sphere intersection can have?", "type": "mc", "opts": ["0, 1, or 2 solutions", "Always 1", "Always 2", "Always 0"], "ans": "0, 1, or 2 solutions", "exp": "Ray can miss, tangent (1), or pass through (2) a sphere.", "cat": "geometry", "diff": 2},
    {"q": "Frustum is?", "type": "mc", "opts": ["Truncated pyramid (camera view)", "Sphere", "Cube", "Cylinder"], "ans": "Truncated pyramid (camera view)", "exp": "View frustum is the visible region between near and far planes.", "cat": "geometry", "diff": 2},
    {"q": "Frustum culling removes?", "type": "mc", "opts": ["Objects outside view", "Visible objects", "All objects", "Textures only"], "ans": "Objects outside view", "exp": "Culling skips rendering objects not in the camera frustum.", "cat": "geometry", "diff": 2},
    {"q": "AABB-AABB intersection checks?", "type": "mc", "opts": ["Overlap on all 3 axes", "Just one axis", "Diagonal only", "Volume calculation"], "ans": "Overlap on all 3 axes", "exp": "AABBs intersect only if they overlap on X, Y, and Z simultaneously.", "cat": "geometry", "diff": 2},
    {"q": "Triangle winding order determines?", "type": "mc", "opts": ["Front vs back face", "Color", "Size", "Texture"], "ans": "Front vs back face", "exp": "Clockwise vs counter-clockwise winding defines which side is front.", "cat": "geometry", "diff": 2},
    {"q": "Surface area of sphere?", "type": "mc", "opts": ["4πr²", "πr²", "2πr", "(4/3)πr³"], "ans": "4πr²", "exp": "Sphere surface area is 4 times pi times radius squared.", "cat": "geometry", "diff": 2},
    {"q": "Volume of sphere?", "type": "mc", "opts": ["(4/3)πr³", "4πr²", "πr²h", "4πr³"], "ans": "(4/3)πr³", "exp": "Sphere volume is (4/3) times pi times radius cubed.", "cat": "geometry", "diff": 2},
    {"q": "Signed area of triangle can be?", "type": "mc", "opts": ["Positive or negative", "Only positive", "Only zero", "Only negative"], "ans": "Positive or negative", "exp": "Signed area indicates winding direction (CW vs CCW).", "cat": "geometry", "diff": 3},
    {"q": "Convex polygon has?", "type": "mc", "opts": ["All interior angles < 180°", "At least one angle > 180°", "No angles", "Only right angles"], "ans": "All interior angles < 180°", "exp": "Convex shapes have no inward-pointing angles.", "cat": "geometry", "diff": 2},
    {"q": "Voronoi diagram partitions space by?", "type": "mc", "opts": ["Nearest seed point", "Random colors", "Equal areas", "Triangle count"], "ans": "Nearest seed point", "exp": "Voronoi cells contain all points closest to each seed.", "cat": "geometry", "diff": 3},
    {"q": "Delaunay triangulation maximizes?", "type": "mc", "opts": ["Minimum angle", "Maximum angle", "Edge count", "Vertex count"], "ans": "Minimum angle", "exp": "Delaunay avoids skinny triangles by maximizing smallest angles.", "cat": "geometry", "diff": 3},
    {"q": "Bezier curve with 4 points is degree?", "type": "mc", "opts": ["3 (cubic)", "4", "2", "1"], "ans": "3 (cubic)", "exp": "Degree = number of control points - 1.", "cat": "geometry", "diff": 2},
    {"q": "B-spline advantage over Bezier?", "type": "mc", "opts": ["Local control", "Simpler math", "Always passes through points", "Fewer points needed"], "ans": "Local control", "exp": "B-splines let you modify part of curve without affecting the whole.", "cat": "geometry", "diff": 3},
    {"q": "NURBS stands for?", "type": "mc", "opts": ["Non-Uniform Rational B-Spline", "New Unified Render Base System", "Normal UV Rotation Blend", "Node Update Render Batch"], "ans": "Non-Uniform Rational B-Spline", "exp": "NURBS allow precise representation of both curves and surfaces.", "cat": "geometry", "diff": 3},
    {"q": "Catmull-Rom spline passes through?", "type": "mc", "opts": ["All control points", "No control points", "Only endpoints", "Only midpoints"], "ans": "All control points", "exp": "Catmull-Rom interpolates through all given points.", "cat": "geometry", "diff": 3},
    
    # Rotations & Quaternions (20)
    {"q": "Quaternion has how many components?", "type": "mc", "opts": ["4 (w, x, y, z)", "3", "2", "1"], "ans": "4 (w, x, y, z)", "exp": "Quaternions have one real (w) and three imaginary (x,y,z) parts.", "cat": "rotations", "diff": 2},
    {"q": "Unit quaternion has magnitude?", "type": "mc", "opts": ["1", "0", "4", "Varies"], "ans": "1", "exp": "Unit quaternions (for rotation) have length 1.", "cat": "rotations", "diff": 2},
    {"q": "Gimbal lock affects?", "type": "mc", "opts": ["Euler angles", "Quaternions", "Matrices only", "All rotation methods"], "ans": "Euler angles", "exp": "Gimbal lock is a problem specific to Euler angle representation.", "cat": "rotations", "diff": 2},
    {"q": "Quaternion multiplication is?", "type": "mc", "opts": ["Non-commutative", "Commutative", "Undefined", "Same as addition"], "ans": "Non-commutative", "exp": "Quaternion multiplication order matters (like matrices).", "cat": "rotations", "diff": 2},
    {"q": "SLERP stands for?", "type": "mc", "opts": ["Spherical Linear Interpolation", "Simple Linear Rotation Path", "Standard Lerp", "Smooth Linear Expression"], "ans": "Spherical Linear Interpolation", "exp": "SLERP interpolates rotations along the shortest arc.", "cat": "rotations", "diff": 2},
    {"q": "Why use SLERP over LERP for rotations?", "type": "mc", "opts": ["Constant angular velocity", "Faster computation", "Uses less memory", "Simpler code"], "ans": "Constant angular velocity", "exp": "SLERP maintains constant rotation speed; LERP can speed up mid-rotation.", "cat": "rotations", "diff": 3},
    {"q": "Quaternion inverse for unit quaternion?", "type": "mc", "opts": ["Conjugate", "Negative", "Square", "Same quaternion"], "ans": "Conjugate", "exp": "For unit quaternions, inverse equals conjugate (negate x,y,z).", "cat": "rotations", "diff": 3},
    {"q": "Identity quaternion is?", "type": "mc", "opts": ["(1, 0, 0, 0)", "(0, 0, 0, 0)", "(0, 1, 0, 0)", "(0, 0, 0, 1)"], "ans": "(1, 0, 0, 0)", "exp": "Identity quaternion has w=1 and zero imaginary parts.", "cat": "rotations", "diff": 2},
    {"q": "Euler angles have how many rotations?", "type": "mc", "opts": ["3 (pitch, yaw, roll)", "1", "2", "4"], "ans": "3 (pitch, yaw, roll)", "exp": "Euler angles specify rotations around 3 axes.", "cat": "rotations", "diff": 1},
    {"q": "Rodrigues' rotation formula uses?", "type": "mc", "opts": ["Axis and angle", "Three angles", "Quaternion only", "Matrix only"], "ans": "Axis and angle", "exp": "Rodrigues rotates a vector around an arbitrary axis by an angle.", "cat": "rotations", "diff": 3},
    {"q": "To combine rotations with quaternions?", "type": "mc", "opts": ["Multiply them", "Add them", "Subtract them", "Divide them"], "ans": "Multiply them", "exp": "Quaternion multiplication composes rotations.", "cat": "rotations", "diff": 2},
    {"q": "Rotating vector v by quaternion q uses?", "type": "mc", "opts": ["q × v × q⁻¹", "q + v", "q × v", "v × q"], "ans": "q × v × q⁻¹", "exp": "Vector rotation requires the sandwich product qvq⁻¹.", "cat": "rotations", "diff": 3},
    {"q": "Double cover in quaternions means?", "type": "mc", "opts": ["q and -q represent same rotation", "Two rotations needed", "Twice the speed", "Double precision"], "ans": "q and -q represent same rotation", "exp": "Both q and its negation rotate the same way.", "cat": "rotations", "diff": 3},
    {"q": "Axis-angle representation uses?", "type": "mc", "opts": ["Unit vector and angle", "Three angles", "Four angles", "Two vectors"], "ans": "Unit vector and angle", "exp": "Axis-angle specifies rotation axis direction and rotation amount.", "cat": "rotations", "diff": 2},
    {"q": "Converting quaternion to matrix produces?", "type": "mc", "opts": ["3x3 rotation matrix", "4x4 only", "2x2 matrix", "1x4 vector"], "ans": "3x3 rotation matrix", "exp": "Quaternion converts to 3x3 rotation (or 4x4 with no translation).", "cat": "rotations", "diff": 2},
    {"q": "Look-at rotation calculates?", "type": "mc", "opts": ["Rotation to face target", "Distance to target", "Target color", "Path to target"], "ans": "Rotation to face target", "exp": "Look-at computes orientation to point at a target position.", "cat": "rotations", "diff": 2},
    {"q": "Angular velocity is best stored as?", "type": "mc", "opts": ["Vector (axis × speed)", "Single angle", "Quaternion", "Matrix"], "ans": "Vector (axis × speed)", "exp": "Angular velocity vector's direction is axis, magnitude is speed.", "cat": "rotations", "diff": 3},
    {"q": "Spherical coordinates use?", "type": "mc", "opts": ["Radius, theta, phi", "x, y, z", "Quaternion", "Two angles only"], "ans": "Radius, theta, phi", "exp": "Spherical coords: radius and two angles (azimuth, elevation).", "cat": "rotations", "diff": 2},
    {"q": "Exponential map for rotations?", "type": "mc", "opts": ["Converts axis-angle to rotation", "Computes logarithm", "Adds rotations", "Scales rotation"], "ans": "Converts axis-angle to rotation", "exp": "Exponential map converts rotation vector to rotation representation.", "cat": "rotations", "diff": 4},
    {"q": "Rotation interpolation artifact?", "type": "mc", "opts": ["Taking the long path", "Color banding", "Texture seam", "Audio click"], "ans": "Taking the long path", "exp": "Naive interpolation can rotate the long way (>180°).", "cat": "rotations", "diff": 3},
    
    # Noise & Procedural (20)
    {"q": "Perlin noise is?", "type": "mc", "opts": ["Gradient noise", "Value noise", "White noise", "Blue noise"], "ans": "Gradient noise", "exp": "Perlin noise interpolates between random gradients at grid points.", "cat": "noise", "diff": 2},
    {"q": "Simplex noise advantage over Perlin?", "type": "mc", "opts": ["Fewer artifacts, faster in higher dimensions", "Simpler to implement", "Better random", "Uses less memory"], "ans": "Fewer artifacts, faster in higher dimensions", "exp": "Simplex has fewer directional artifacts and scales better to higher D.", "cat": "noise", "diff": 3},
    {"q": "Octaves in fractal noise add?", "type": "mc", "opts": ["Detail at different scales", "Color", "Animation", "Sound"], "ans": "Detail at different scales", "exp": "Each octave adds finer detail with reduced amplitude.", "cat": "noise", "diff": 2},
    {"q": "Lacunarity in FBM controls?", "type": "mc", "opts": ["Frequency multiplier between octaves", "Amplitude", "Color", "Speed"], "ans": "Frequency multiplier between octaves", "exp": "Lacunarity (usually 2.0) multiplies frequency each octave.", "cat": "noise", "diff": 3},
    {"q": "Persistence/gain in FBM controls?", "type": "mc", "opts": ["Amplitude multiplier between octaves", "Frequency", "Seed", "Offset"], "ans": "Amplitude multiplier between octaves", "exp": "Persistence (usually 0.5) reduces amplitude each octave.", "cat": "noise", "diff": 3},
    {"q": "FBM stands for?", "type": "mc", "opts": ["Fractal Brownian Motion", "Fast Blend Mode", "Frame Buffer Memory", "Fixed Byte Map"], "ans": "Fractal Brownian Motion", "exp": "FBM sums multiple noise octaves for natural-looking results.", "cat": "noise", "diff": 2},
    {"q": "Worley/Voronoi noise creates?", "type": "mc", "opts": ["Cell-like patterns", "Smooth gradients", "Stripes", "Solid colors"], "ans": "Cell-like patterns", "exp": "Worley noise measures distance to nearest feature points.", "cat": "noise", "diff": 3},
    {"q": "White noise has?", "type": "mc", "opts": ["Equal power at all frequencies", "Only low frequencies", "Only high frequencies", "No frequencies"], "ans": "Equal power at all frequencies", "exp": "White noise is completely random with flat spectrum.", "cat": "noise", "diff": 2},
    {"q": "Blue noise has?", "type": "mc", "opts": ["Minimal low frequency content", "Only low frequencies", "Equal all frequencies", "No pattern"], "ans": "Minimal low frequency content", "exp": "Blue noise lacks low-frequency patterns, good for sampling.", "cat": "noise", "diff": 3},
    {"q": "Domain warping uses noise to?", "type": "mc", "opts": ["Distort input coordinates", "Change colors", "Add sound", "Compress data"], "ans": "Distort input coordinates", "exp": "Domain warping offsets lookup position using noise values.", "cat": "noise", "diff": 3},
    {"q": "Turbulence noise uses?", "type": "mc", "opts": ["Absolute value of noise", "Negative noise", "Squared noise", "Noise derivatives"], "ans": "Absolute value of noise", "exp": "Turbulence takes abs(noise) creating sharp ridges.", "cat": "noise", "diff": 3},
    {"q": "Ridged noise is created by?", "type": "mc", "opts": ["1 - abs(noise)", "noise²", "noise + 1", "noise × 2"], "ans": "1 - abs(noise)", "exp": "Ridged noise inverts turbulence to create ridge-like features.", "cat": "noise", "diff": 3},
    {"q": "Noise seed affects?", "type": "mc", "opts": ["Random number sequence", "Amplitude", "Frequency", "Octave count"], "ans": "Random number sequence", "exp": "Same seed produces identical noise; different seeds vary the pattern.", "cat": "noise", "diff": 1},
    {"q": "Seamless/tileable noise requires?", "type": "mc", "opts": ["Wrapping at boundaries", "Higher resolution", "More octaves", "Different seed"], "ans": "Wrapping at boundaries", "exp": "Tileable noise matches values at opposite edges.", "cat": "noise", "diff": 3},
    {"q": "Procedural generation advantage?", "type": "mc", "opts": ["Infinite variety from small data", "Better quality", "Faster loading", "Simpler code"], "ans": "Infinite variety from small data", "exp": "Procedures generate vast content from compact algorithms.", "cat": "noise", "diff": 1},
    {"q": "Heightmap terrain uses noise for?", "type": "mc", "opts": ["Elevation values", "Texture colors", "Object placement only", "Collision only"], "ans": "Elevation values", "exp": "Noise values become terrain height at each point.", "cat": "noise", "diff": 1},
    {"q": "Erosion simulation improves terrain by?", "type": "mc", "opts": ["Simulating water/sediment flow", "Adding more noise", "Smoothing only", "Random modification"], "ans": "Simulating water/sediment flow", "exp": "Hydraulic erosion carves realistic valleys and deposits sediment.", "cat": "noise", "diff": 3},
    {"q": "Marching cubes extracts?", "type": "mc", "opts": ["Mesh from 3D scalar field", "2D image", "Audio", "Pathfinding grid"], "ans": "Mesh from 3D scalar field", "exp": "Marching cubes creates surface meshes from volumetric data.", "cat": "noise", "diff": 3},
    {"q": "Wave Function Collapse generates?", "type": "mc", "opts": ["Patterns from example constraints", "Audio waves", "Physics simulation", "Network packets"], "ans": "Patterns from example constraints", "exp": "WFC propagates constraints to generate coherent patterns.", "cat": "noise", "diff": 4},
    {"q": "L-systems are used for?", "type": "mc", "opts": ["Plants and fractals", "Audio only", "Networking", "File compression"], "ans": "Plants and fractals", "exp": "L-systems use recursive string rewriting for organic structures.", "cat": "noise", "diff": 3},
]

# ============================================================================
# CS QUIZ BANK - 95 Questions  
# ============================================================================

CS_QUIZZES = [
    # Data Structures (25)
    {"q": "Array access time complexity?", "type": "mc", "opts": ["O(1)", "O(n)", "O(log n)", "O(n²)"], "ans": "O(1)", "exp": "Arrays provide constant-time random access by index.", "cat": "data_structures", "diff": 1},
    {"q": "Linked list insertion at head?", "type": "mc", "opts": ["O(1)", "O(n)", "O(log n)", "O(n²)"], "ans": "O(1)", "exp": "Inserting at linked list head only updates one pointer.", "cat": "data_structures", "diff": 1},
    {"q": "Hash table average lookup?", "type": "mc", "opts": ["O(1)", "O(n)", "O(log n)", "O(n log n)"], "ans": "O(1)", "exp": "Hash tables provide constant average-case lookup.", "cat": "data_structures", "diff": 1},
    {"q": "Binary search tree balanced lookup?", "type": "mc", "opts": ["O(log n)", "O(1)", "O(n)", "O(n²)"], "ans": "O(log n)", "exp": "Balanced BST halves search space each step.", "cat": "data_structures", "diff": 2},
    {"q": "Stack follows which principle?", "type": "mc", "opts": ["LIFO", "FIFO", "Random", "Priority"], "ans": "LIFO", "exp": "Stack is Last-In-First-Out.", "cat": "data_structures", "diff": 1},
    {"q": "Queue follows which principle?", "type": "mc", "opts": ["FIFO", "LIFO", "Random", "Sorted"], "ans": "FIFO", "exp": "Queue is First-In-First-Out.", "cat": "data_structures", "diff": 1},
    {"q": "Priority queue extracts?", "type": "mc", "opts": ["Highest/lowest priority element", "First inserted", "Last inserted", "Random element"], "ans": "Highest/lowest priority element", "exp": "Priority queues dequeue based on priority, not insertion order.", "cat": "data_structures", "diff": 2},
    {"q": "Heap extract-min complexity?", "type": "mc", "opts": ["O(log n)", "O(1)", "O(n)", "O(n log n)"], "ans": "O(log n)", "exp": "Heap must reheapify after removal, taking O(log n).", "cat": "data_structures", "diff": 2},
    {"q": "Quadtree is used for?", "type": "mc", "opts": ["2D spatial partitioning", "Sorting", "Audio processing", "Text search"], "ans": "2D spatial partitioning", "exp": "Quadtrees recursively divide 2D space into four quadrants.", "cat": "data_structures", "diff": 2},
    {"q": "Octree divides space into?", "type": "mc", "opts": ["8 octants", "4 quadrants", "2 halves", "16 sections"], "ans": "8 octants", "exp": "Octrees split 3D space into 8 children per node.", "cat": "data_structures", "diff": 2},
    {"q": "BVH stands for?", "type": "mc", "opts": ["Bounding Volume Hierarchy", "Binary Vector Hash", "Basic View Handler", "Buffered Vertex Handle"], "ans": "Bounding Volume Hierarchy", "exp": "BVH organizes objects in nested bounding volumes for fast culling.", "cat": "data_structures", "diff": 2},
    {"q": "Spatial hashing maps?", "type": "mc", "opts": ["Position to bucket", "Name to ID", "Color to texture", "Sound to channel"], "ans": "Position to bucket", "exp": "Spatial hashing assigns objects to grid cells by position.", "cat": "data_structures", "diff": 2},
    {"q": "k-d tree is good for?", "type": "mc", "opts": ["Nearest neighbor search", "Sorting", "Text parsing", "Audio mixing"], "ans": "Nearest neighbor search", "exp": "k-d trees efficiently find closest points in k dimensions.", "cat": "data_structures", "diff": 3},
    {"q": "Ring buffer advantage?", "type": "mc", "opts": ["Fixed memory, no allocation", "Unlimited size", "Sorted order", "Random access"], "ans": "Fixed memory, no allocation", "exp": "Ring buffers reuse fixed memory in a circular fashion.", "cat": "data_structures", "diff": 2},
    {"q": "Object pool reduces?", "type": "mc", "opts": ["Allocation overhead", "Memory usage", "Code complexity", "Rendering time"], "ans": "Allocation overhead", "exp": "Pools pre-allocate objects to avoid runtime allocation.", "cat": "data_structures", "diff": 2},
    {"q": "Entity Component System separates?", "type": "mc", "opts": ["Data from behavior", "Graphics from audio", "Input from output", "Files from memory"], "ans": "Data from behavior", "exp": "ECS stores data in components, behavior in systems.", "cat": "data_structures", "diff": 2},
    {"q": "Sparse set advantage?", "type": "mc", "opts": ["O(1) add/remove/contains", "Sorted iteration", "Smallest memory", "Thread safety"], "ans": "O(1) add/remove/contains", "exp": "Sparse sets provide constant-time operations for integer keys.", "cat": "data_structures", "diff": 3},
    {"q": "Trie is optimal for?", "type": "mc", "opts": ["Prefix matching", "Numeric sorting", "3D graphics", "Audio playback"], "ans": "Prefix matching", "exp": "Tries store strings sharing prefixes efficiently.", "cat": "data_structures", "diff": 2},
    {"q": "Graph adjacency list space?", "type": "mc", "opts": ["O(V + E)", "O(V²)", "O(V)", "O(E²)"], "ans": "O(V + E)", "exp": "Adjacency list stores each vertex and edge once.", "cat": "data_structures", "diff": 2},
    {"q": "Graph adjacency matrix space?", "type": "mc", "opts": ["O(V²)", "O(V + E)", "O(V)", "O(E)"], "ans": "O(V²)", "exp": "Matrix stores V×V entries regardless of edge count.", "cat": "data_structures", "diff": 2},
    {"q": "LRU cache evicts?", "type": "mc", "opts": ["Least recently used", "Most recently used", "Random", "Oldest"], "ans": "Least recently used", "exp": "LRU removes items not accessed for longest time.", "cat": "data_structures", "diff": 2},
    {"q": "Bloom filter can have?", "type": "mc", "opts": ["False positives only", "False negatives only", "Both", "Neither"], "ans": "False positives only", "exp": "Bloom filters may say 'maybe present' but never miss actual items.", "cat": "data_structures", "diff": 3},
    {"q": "Skip list provides?", "type": "mc", "opts": ["Probabilistic O(log n) search", "O(1) search", "O(n) always", "Sorted by insertion"], "ans": "Probabilistic O(log n) search", "exp": "Skip lists use random tower heights for efficient search.", "cat": "data_structures", "diff": 3},
    {"q": "Disjoint set (Union-Find) supports?", "type": "mc", "opts": ["Efficient union and find operations", "Sorting", "Searching text", "3D rendering"], "ans": "Efficient union and find operations", "exp": "Union-Find tracks connected components efficiently.", "cat": "data_structures", "diff": 3},
    {"q": "Interval tree queries?", "type": "mc", "opts": ["Overlapping intervals", "Point locations", "Shortest paths", "Color values"], "ans": "Overlapping intervals", "exp": "Interval trees find all intervals overlapping a query range.", "cat": "data_structures", "diff": 3},
    
    # Algorithms (25)
    {"q": "Binary search requires?", "type": "mc", "opts": ["Sorted array", "Any array", "Linked list", "Hash table"], "ans": "Sorted array", "exp": "Binary search only works on sorted data.", "cat": "algorithms", "diff": 1},
    {"q": "Quicksort average complexity?", "type": "mc", "opts": ["O(n log n)", "O(n²)", "O(n)", "O(log n)"], "ans": "O(n log n)", "exp": "Quicksort averages n log n with good pivot selection.", "cat": "algorithms", "diff": 2},
    {"q": "Merge sort space complexity?", "type": "mc", "opts": ["O(n)", "O(1)", "O(log n)", "O(n²)"], "ans": "O(n)", "exp": "Merge sort needs O(n) auxiliary space for merging.", "cat": "algorithms", "diff": 2},
    {"q": "A* pathfinding uses?", "type": "mc", "opts": ["f = g + h", "f = g - h", "f = g × h", "f = h only"], "ans": "f = g + h", "exp": "A* combines actual cost (g) with heuristic estimate (h).", "cat": "algorithms", "diff": 2},
    {"q": "Dijkstra's algorithm finds?", "type": "mc", "opts": ["Shortest paths from source", "Longest path", "All cycles", "Minimum spanning tree"], "ans": "Shortest paths from source", "exp": "Dijkstra finds shortest paths from one vertex to all others.", "cat": "algorithms", "diff": 2},
    {"q": "BFS uses which data structure?", "type": "mc", "opts": ["Queue", "Stack", "Heap", "Array"], "ans": "Queue", "exp": "Breadth-First Search uses a queue for level-order traversal.", "cat": "algorithms", "diff": 1},
    {"q": "DFS uses which data structure?", "type": "mc", "opts": ["Stack", "Queue", "Heap", "Hash table"], "ans": "Stack", "exp": "Depth-First Search uses a stack (or recursion).", "cat": "algorithms", "diff": 1},
    {"q": "Admissible heuristic means?", "type": "mc", "opts": ["Never overestimates", "Always exact", "Always overestimates", "Random"], "ans": "Never overestimates", "exp": "Admissible heuristics guarantee optimal A* solutions.", "cat": "algorithms", "diff": 3},
    {"q": "Manhattan distance for grid heuristic?", "type": "mc", "opts": ["|dx| + |dy|", "√(dx² + dy²)", "max(|dx|, |dy|)", "dx × dy"], "ans": "|dx| + |dy|", "exp": "Manhattan distance sums absolute differences (no diagonals).", "cat": "algorithms", "diff": 2},
    {"q": "Jump Point Search optimizes?", "type": "mc", "opts": ["A* on uniform grids", "Dijkstra", "BFS", "DFS"], "ans": "A* on uniform grids", "exp": "JPS prunes symmetric paths on uniform-cost grids.", "cat": "algorithms", "diff": 3},
    {"q": "Navmesh stores?", "type": "mc", "opts": ["Walkable polygon regions", "Pixel colors", "Audio data", "Network packets"], "ans": "Walkable polygon regions", "exp": "Navigation meshes define walkable areas as convex polygons.", "cat": "algorithms", "diff": 2},
    {"q": "Funnel algorithm computes?", "type": "mc", "opts": ["Shortest path through navmesh", "Longest path", "Audio reverb", "Texture mapping"], "ans": "Shortest path through navmesh", "exp": "Funnel smooths paths through navmesh portals.", "cat": "algorithms", "diff": 3},
    {"q": "Flow field pathfinding advantage?", "type": "mc", "opts": ["Many agents, one target", "One agent, many targets", "No computation", "Exact paths only"], "ans": "Many agents, one target", "exp": "Flow fields compute once for unlimited agents to reach same goal.", "cat": "algorithms", "diff": 3},
    {"q": "Dynamic programming requires?", "type": "mc", "opts": ["Optimal substructure", "Random input", "Sorted data", "Graph structure"], "ans": "Optimal substructure", "exp": "DP works when optimal solutions contain optimal sub-solutions.", "cat": "algorithms", "diff": 2},
    {"q": "Memoization is?", "type": "mc", "opts": ["Caching function results", "Memory allocation", "Sorting technique", "Search algorithm"], "ans": "Caching function results", "exp": "Memoization stores computed results to avoid recalculation.", "cat": "algorithms", "diff": 2},
    {"q": "Greedy algorithm characteristic?", "type": "mc", "opts": ["Local optimal choices", "Global optimal guaranteed", "Exhaustive search", "Random selection"], "ans": "Local optimal choices", "exp": "Greedy makes locally optimal choices hoping for global optimum.", "cat": "algorithms", "diff": 2},
    {"q": "Divide and conquer splits problem into?", "type": "mc", "opts": ["Smaller subproblems", "Larger problems", "Equal parts always", "Random pieces"], "ans": "Smaller subproblems", "exp": "D&C breaks problems into smaller pieces solved recursively.", "cat": "algorithms", "diff": 2},
    {"q": "Rabin-Karp uses?", "type": "mc", "opts": ["Rolling hash for string search", "Binary search", "Sorting", "Graph traversal"], "ans": "Rolling hash for string search", "exp": "Rabin-Karp uses hashing for efficient substring matching.", "cat": "algorithms", "diff": 3},
    {"q": "KMP algorithm improves?", "type": "mc", "opts": ["String pattern matching", "Sorting", "Graph search", "Numeric computation"], "ans": "String pattern matching", "exp": "KMP avoids re-examining characters using failure function.", "cat": "algorithms", "diff": 3},
    {"q": "Minimum spanning tree algorithms?", "type": "mc", "opts": ["Kruskal's, Prim's", "Dijkstra's, A*", "BFS, DFS", "Quick, Merge"], "ans": "Kruskal's, Prim's", "exp": "Kruskal's and Prim's algorithms find minimum spanning trees.", "cat": "algorithms", "diff": 2},
    {"q": "Topological sort requires?", "type": "mc", "opts": ["Directed acyclic graph", "Undirected graph", "Weighted edges", "Cycles"], "ans": "Directed acyclic graph", "exp": "Topological sort only works on DAGs (no cycles).", "cat": "algorithms", "diff": 2},
    {"q": "Flood fill uses?", "type": "mc", "opts": ["BFS or DFS", "Sorting", "Hashing", "Binary search"], "ans": "BFS or DFS", "exp": "Flood fill spreads using graph traversal from a starting point.", "cat": "algorithms", "diff": 2},
    {"q": "Convex hull algorithms?", "type": "mc", "opts": ["Graham scan, Jarvis march", "A*, Dijkstra", "Quick, Merge", "BFS, DFS"], "ans": "Graham scan, Jarvis march", "exp": "Graham scan and Jarvis march find convex hulls of point sets.", "cat": "algorithms", "diff": 3},
    {"q": "Line sweep technique processes?", "type": "mc", "opts": ["Events in sorted order", "Random events", "All at once", "Backwards"], "ans": "Events in sorted order", "exp": "Sweep line processes geometric events in coordinate order.", "cat": "algorithms", "diff": 3},
    {"q": "Ear clipping triangulates?", "type": "mc", "opts": ["Simple polygons", "3D meshes", "Point clouds", "Curves"], "ans": "Simple polygons", "exp": "Ear clipping removes triangular 'ears' from simple polygons.", "cat": "algorithms", "diff": 3},
    
    # Graphics & Rendering (25)
    {"q": "Vertex shader runs per?", "type": "mc", "opts": ["Vertex", "Pixel", "Triangle", "Frame"], "ans": "Vertex", "exp": "Vertex shaders process each vertex independently.", "cat": "graphics", "diff": 1},
    {"q": "Fragment/pixel shader runs per?", "type": "mc", "opts": ["Pixel/fragment", "Vertex", "Triangle", "Mesh"], "ans": "Pixel/fragment", "exp": "Fragment shaders compute color for each pixel.", "cat": "graphics", "diff": 1},
    {"q": "GPU excels at?", "type": "mc", "opts": ["Parallel processing", "Sequential tasks", "File I/O", "Networking"], "ans": "Parallel processing", "exp": "GPUs have thousands of cores for massive parallelism.", "cat": "graphics", "diff": 1},
    {"q": "Draw call is?", "type": "mc", "opts": ["CPU command to GPU to render", "Pixel color", "Vertex position", "Texture coordinate"], "ans": "CPU command to GPU to render", "exp": "Draw calls tell GPU to render geometry with current state.", "cat": "graphics", "diff": 2},
    {"q": "Batching reduces?", "type": "mc", "opts": ["Draw call count", "Texture quality", "Vertex count", "Memory usage"], "ans": "Draw call count", "exp": "Batching combines objects to reduce expensive draw calls.", "cat": "graphics", "diff": 2},
    {"q": "Instancing allows?", "type": "mc", "opts": ["Drawing many copies efficiently", "Better textures", "Faster physics", "Audio mixing"], "ans": "Drawing many copies efficiently", "exp": "Instancing renders many instances of same mesh in one call.", "cat": "graphics", "diff": 2},
    {"q": "Z-buffer stores?", "type": "mc", "opts": ["Depth values", "Color values", "Normal vectors", "Texture coords"], "ans": "Depth values", "exp": "Z-buffer tracks closest fragment depth at each pixel.", "cat": "graphics", "diff": 1},
    {"q": "Stencil buffer is used for?", "type": "mc", "opts": ["Masking and effects", "Depth testing", "Color blending", "Vertex animation"], "ans": "Masking and effects", "exp": "Stencil buffer enables masking, mirrors, shadows, etc.", "cat": "graphics", "diff": 2},
    {"q": "Deferred rendering advantage?", "type": "mc", "opts": ["Many lights efficiently", "Transparency", "Simple implementation", "Less memory"], "ans": "Many lights efficiently", "exp": "Deferred rendering decouples geometry from lighting.", "cat": "graphics", "diff": 3},
    {"q": "G-buffer contains?", "type": "mc", "opts": ["Geometry attributes (normals, depth, etc.)", "Only color", "Audio data", "Physics state"], "ans": "Geometry attributes (normals, depth, etc.)", "exp": "G-buffer stores position, normals, albedo for deferred lighting.", "cat": "graphics", "diff": 3},
    {"q": "Forward rendering handles transparency?", "type": "mc", "opts": ["Better than deferred", "Worse than deferred", "Equally", "Cannot handle"], "ans": "Better than deferred", "exp": "Forward rendering handles transparency more naturally.", "cat": "graphics", "diff": 3},
    {"q": "Normal mapping stores?", "type": "mc", "opts": ["Per-pixel normals in texture", "Vertex positions", "Colors only", "Depth values"], "ans": "Per-pixel normals in texture", "exp": "Normal maps encode surface detail as per-pixel normals.", "cat": "graphics", "diff": 2},
    {"q": "PBR stands for?", "type": "mc", "opts": ["Physically Based Rendering", "Pixel Buffer Render", "Progressive Blend Rate", "Post Blur Reflection"], "ans": "Physically Based Rendering", "exp": "PBR uses physical light models for realistic materials.", "cat": "graphics", "diff": 2},
    {"q": "Albedo in PBR is?", "type": "mc", "opts": ["Base color without lighting", "Reflection amount", "Surface roughness", "Normal direction"], "ans": "Base color without lighting", "exp": "Albedo is the diffuse color before any lighting is applied.", "cat": "graphics", "diff": 2},
    {"q": "Metallic workflow value of 1 means?", "type": "mc", "opts": ["Fully metallic", "Non-metallic", "Transparent", "Emissive"], "ans": "Fully metallic", "exp": "Metallic = 1 makes surface behave like metal.", "cat": "graphics", "diff": 2},
    {"q": "Roughness of 0 means?", "type": "mc", "opts": ["Perfect mirror", "Completely rough", "Invisible", "Emissive"], "ans": "Perfect mirror", "exp": "Zero roughness creates sharp, mirror-like reflections.", "cat": "graphics", "diff": 2},
    {"q": "Screen Space Ambient Occlusion approximates?", "type": "mc", "opts": ["Contact shadows", "Direct lighting", "Reflections", "Transparency"], "ans": "Contact shadows", "exp": "SSAO darkens creases and corners using depth buffer.", "cat": "graphics", "diff": 2},
    {"q": "Bloom effect creates?", "type": "mc", "opts": ["Glow around bright areas", "Shadows", "Reflections", "Motion blur"], "ans": "Glow around bright areas", "exp": "Bloom bleeds bright pixels into surrounding area.", "cat": "graphics", "diff": 2},
    {"q": "HDR rendering uses?", "type": "mc", "opts": ["Values beyond 0-1 range", "Only 8-bit color", "Fewer colors", "No lighting"], "ans": "Values beyond 0-1 range", "exp": "HDR allows brightness values exceeding standard 0-1 range.", "cat": "graphics", "diff": 2},
    {"q": "Tone mapping converts?", "type": "mc", "opts": ["HDR to displayable LDR", "LDR to HDR", "Color to grayscale", "3D to 2D"], "ans": "HDR to displayable LDR", "exp": "Tone mapping compresses HDR values to displayable range.", "cat": "graphics", "diff": 3},
    {"q": "Mipmaps are?", "type": "mc", "opts": ["Pre-filtered texture levels", "Normal maps", "Depth buffers", "Vertex data"], "ans": "Pre-filtered texture levels", "exp": "Mipmaps are progressively smaller texture versions.", "cat": "graphics", "diff": 2},
    {"q": "Anisotropic filtering improves?", "type": "mc", "opts": ["Textures at oblique angles", "Vertex colors", "Audio quality", "Physics accuracy"], "ans": "Textures at oblique angles", "exp": "Anisotropic filtering sharpens textures viewed at angles.", "cat": "graphics", "diff": 2},
    {"q": "Shadow mapping compares?", "type": "mc", "opts": ["Fragment depth to shadow map", "Colors", "Normals", "Velocities"], "ans": "Fragment depth to shadow map", "exp": "Shadow maps compare scene depth to light's depth texture.", "cat": "graphics", "diff": 2},
    {"q": "Cascaded shadow maps improve?", "type": "mc", "opts": ["Shadow quality at different distances", "Color accuracy", "Particle count", "Audio fidelity"], "ans": "Shadow quality at different distances", "exp": "CSM uses multiple shadow maps for near to far distances.", "cat": "graphics", "diff": 3},
    {"q": "Ray tracing advantage?", "type": "mc", "opts": ["Accurate reflections and global illumination", "Faster than rasterization", "Less memory", "Simpler code"], "ans": "Accurate reflections and global illumination", "exp": "Ray tracing naturally handles reflections, refractions, shadows.", "cat": "graphics", "diff": 2},
    
    # Game AI (20)
    {"q": "Behavior tree node types?", "type": "mc", "opts": ["Composite, Decorator, Leaf", "If, Else, Loop", "Start, End, Middle", "Input, Output, Process"], "ans": "Composite, Decorator, Leaf", "exp": "BTs have composites (sequence/selector), decorators, and leaf actions.", "cat": "ai", "diff": 2},
    {"q": "Sequence node succeeds when?", "type": "mc", "opts": ["All children succeed", "Any child succeeds", "First child succeeds", "Random"], "ans": "All children succeed", "exp": "Sequence runs children in order, failing if any fails.", "cat": "ai", "diff": 2},
    {"q": "Selector node succeeds when?", "type": "mc", "opts": ["Any child succeeds", "All children succeed", "None succeed", "Random"], "ans": "Any child succeeds", "exp": "Selector tries children until one succeeds.", "cat": "ai", "diff": 2},
    {"q": "FSM stands for?", "type": "mc", "opts": ["Finite State Machine", "Fast State Manager", "Fixed System Memory", "Frame Sync Mode"], "ans": "Finite State Machine", "exp": "FSM models AI as states with transitions between them.", "cat": "ai", "diff": 1},
    {"q": "HFSM adds?", "type": "mc", "opts": ["Hierarchy to FSM", "Speed", "Memory", "Graphics"], "ans": "Hierarchy to FSM", "exp": "Hierarchical FSM nests state machines for organization.", "cat": "ai", "diff": 2},
    {"q": "Utility AI selects actions by?", "type": "mc", "opts": ["Scoring and comparing utilities", "Random choice", "Fixed order", "Player input"], "ans": "Scoring and comparing utilities", "exp": "Utility AI evaluates and picks highest-scoring action.", "cat": "ai", "diff": 2},
    {"q": "GOAP stands for?", "type": "mc", "opts": ["Goal-Oriented Action Planning", "Game Object Action Process", "General Output Array Parser", "Graphics Optimization API"], "ans": "Goal-Oriented Action Planning", "exp": "GOAP plans action sequences to achieve goals.", "cat": "ai", "diff": 3},
    {"q": "Blackboard in AI is?", "type": "mc", "opts": ["Shared data storage", "Drawing surface", "Error log", "Network buffer"], "ans": "Shared data storage", "exp": "Blackboards store shared knowledge for AI decision-making.", "cat": "ai", "diff": 2},
    {"q": "Steering behaviors include?", "type": "mc", "opts": ["Seek, Flee, Wander", "Jump, Crouch, Sprint", "Attack, Defend, Heal", "Save, Load, Quit"], "ans": "Seek, Flee, Wander", "exp": "Steering behaviors are movement algorithms like seek and avoid.", "cat": "ai", "diff": 2},
    {"q": "Flocking combines?", "type": "mc", "opts": ["Separation, Alignment, Cohesion", "Speed, Direction, Color", "Attack, Defend, Flee", "Jump, Run, Walk"], "ans": "Separation, Alignment, Cohesion", "exp": "Boids flocking uses three simple rules for group behavior.", "cat": "ai", "diff": 2},
    {"q": "Influence map shows?", "type": "mc", "opts": ["Spatial importance/threat", "Texture data", "Audio levels", "Network traffic"], "ans": "Spatial importance/threat", "exp": "Influence maps track control, threat, or interest across space.", "cat": "ai", "diff": 3},
    {"q": "Monte Carlo Tree Search is used in?", "type": "mc", "opts": ["Game playing AI", "Pathfinding only", "Audio processing", "Rendering"], "ans": "Game playing AI", "exp": "MCTS explores game trees using random playouts.", "cat": "ai", "diff": 3},
    {"q": "Minimax algorithm assumes?", "type": "mc", "opts": ["Opponent plays optimally", "Opponent plays randomly", "No opponent", "Cooperative play"], "ans": "Opponent plays optimally", "exp": "Minimax assumes adversary makes best possible moves.", "cat": "ai", "diff": 3},
    {"q": "Alpha-beta pruning improves?", "type": "mc", "opts": ["Minimax efficiency", "Graphics", "Audio", "Networking"], "ans": "Minimax efficiency", "exp": "Alpha-beta skips branches that can't affect the outcome.", "cat": "ai", "diff": 3},
    {"q": "Perception system handles?", "type": "mc", "opts": ["What AI can see/hear", "Player input", "Graphics", "Networking"], "ans": "What AI can see/hear", "exp": "Perception systems simulate AI senses (sight, sound).", "cat": "ai", "diff": 2},
    {"q": "Line of sight check uses?", "type": "mc", "opts": ["Raycasting", "BFS", "Sorting", "Hashing"], "ans": "Raycasting", "exp": "LoS casts a ray to check for obstructions between points.", "cat": "ai", "diff": 2},
    {"q": "Context steering combines?", "type": "mc", "opts": ["Interest and danger maps", "Colors", "Sounds", "Textures"], "ans": "Interest and danger maps", "exp": "Context steering weights directions by interest vs danger.", "cat": "ai", "diff": 3},
    {"q": "HTN stands for?", "type": "mc", "opts": ["Hierarchical Task Network", "High Texture Normal", "Hash Table Node", "Hard Terrain Navigation"], "ans": "Hierarchical Task Network", "exp": "HTN planning decomposes high-level tasks into primitives.", "cat": "ai", "diff": 3},
    {"q": "Neural network in games used for?", "type": "mc", "opts": ["Learning behaviors, predictions", "Only graphics", "Only audio", "File compression"], "ans": "Learning behaviors, predictions", "exp": "NNs can learn player patterns, generate content, control NPCs.", "cat": "ai", "diff": 2},
    {"q": "Reinforcement learning reward signal?", "type": "mc", "opts": ["Feedback for good/bad actions", "Visual texture", "Audio clip", "Network packet"], "ans": "Feedback for good/bad actions", "exp": "RL agents learn from reward signals indicating success/failure.", "cat": "ai", "diff": 2},
]

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_quiz_bank_info():
    return {
        "name": "CodeDock Comprehensive Quiz Bank v11.6 SOTA",
        "total_quizzes": len(PHYSICS_QUIZZES) + len(MATH_QUIZZES) + len(CS_QUIZZES),
        "physics_quizzes": len(PHYSICS_QUIZZES),
        "math_quizzes": len(MATH_QUIZZES),
        "cs_quizzes": len(CS_QUIZZES),
        "categories": {
            "physics": ["mechanics", "game_physics", "fluids", "soft_body", "constraints"],
            "math": ["linear_algebra", "geometry", "rotations", "noise"],
            "cs": ["data_structures", "algorithms", "graphics", "ai"]
        },
        "difficulty_levels": 4,
        "industry_standard": True
    }

@router.get("/physics")
async def get_physics_quizzes(category: Optional[str] = None, difficulty: Optional[int] = None, count: int = 10):
    quizzes = PHYSICS_QUIZZES
    if category:
        quizzes = [q for q in quizzes if q.get("cat") == category]
    if difficulty:
        quizzes = [q for q in quizzes if q.get("diff") == difficulty]
    selected = random.sample(quizzes, min(count, len(quizzes)))
    return format_quiz_response("physics", selected)

@router.get("/math")
async def get_math_quizzes(category: Optional[str] = None, difficulty: Optional[int] = None, count: int = 10):
    quizzes = MATH_QUIZZES
    if category:
        quizzes = [q for q in quizzes if q.get("cat") == category]
    if difficulty:
        quizzes = [q for q in quizzes if q.get("diff") == difficulty]
    selected = random.sample(quizzes, min(count, len(quizzes)))
    return format_quiz_response("math", selected)

@router.get("/cs")
async def get_cs_quizzes(category: Optional[str] = None, difficulty: Optional[int] = None, count: int = 10):
    quizzes = CS_QUIZZES
    if category:
        quizzes = [q for q in quizzes if q.get("cat") == category]
    if difficulty:
        quizzes = [q for q in quizzes if q.get("diff") == difficulty]
    selected = random.sample(quizzes, min(count, len(quizzes)))
    return format_quiz_response("cs", selected)

@router.get("/all")
async def get_all_quizzes(count_per_subject: int = 5):
    physics = random.sample(PHYSICS_QUIZZES, min(count_per_subject, len(PHYSICS_QUIZZES)))
    math = random.sample(MATH_QUIZZES, min(count_per_subject, len(MATH_QUIZZES)))
    cs = random.sample(CS_QUIZZES, min(count_per_subject, len(CS_QUIZZES)))
    
    all_quizzes = physics + math + cs
    random.shuffle(all_quizzes)
    
    return {
        "quiz_id": f"mixed_{uuid.uuid4().hex[:8]}",
        "type": "mixed",
        "total_questions": len(all_quizzes),
        "questions": [
            {
                "question_id": f"q_{i}",
                "question": q["q"],
                "options": q["opts"],
                "category": q["cat"],
                "difficulty": q["diff"]
            }
            for i, q in enumerate(all_quizzes)
        ]
    }

@router.post("/grade")
async def grade_quiz(answers: List[Dict[str, Any]], subject: str):
    if subject == "physics":
        bank = PHYSICS_QUIZZES
    elif subject == "math":
        bank = MATH_QUIZZES
    elif subject == "cs":
        bank = CS_QUIZZES
    else:
        raise HTTPException(status_code=400, detail="Invalid subject")
    
    results = []
    correct = 0
    
    for ans in answers:
        q_idx = ans.get("question_index", 0)
        user_answer = ans.get("answer", "")
        
        if q_idx < len(bank):
            q = bank[q_idx]
            is_correct = user_answer == q["ans"]
            if is_correct:
                correct += 1
            results.append({
                "question": q["q"][:60] + "...",
                "your_answer": user_answer,
                "correct_answer": q["ans"],
                "is_correct": is_correct,
                "explanation": q["exp"],
                "difficulty": q["diff"]
            })
    
    total = len(answers)
    score = (correct / total * 100) if total > 0 else 0
    xp = correct * 10 + (25 if correct == total else 0)
    
    return {
        "score_percent": round(score, 1),
        "correct": correct,
        "total": total,
        "xp_earned": xp,
        "perfect": correct == total,
        "results": results,
        "grade": get_grade(score)
    }

def format_quiz_response(subject: str, quizzes: List) -> Dict:
    return {
        "quiz_id": f"{subject}_{uuid.uuid4().hex[:8]}",
        "subject": subject,
        "total_questions": len(quizzes),
        "total_xp": len(quizzes) * 10,
        "questions": [
            {
                "question_id": f"{subject}_q{i}",
                "question": q["q"],
                "options": q["opts"],
                "category": q["cat"],
                "difficulty": q["diff"]
            }
            for i, q in enumerate(quizzes)
        ]
    }

def get_grade(score: float) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"
