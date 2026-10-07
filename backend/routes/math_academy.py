"""
Math Academy v16.5 — Complete Mathematics Curriculum
Algebra, Linear Algebra, Geometry, Pre-Calculus, Calculus, Multivariable Calculus
AAA Studio Quality Mathematics Education
"""

from fastapi import APIRouter
from typing import Dict, List, Any

router = APIRouter(prefix="/api/math-academy", tags=["math-academy"])

# =============================================================================
# COMPLETE MATH CURRICULUM
# =============================================================================

MATH_COURSES: Dict[str, Dict[str, Any]] = {
    "algebra": {
        "id": "algebra",
        "name": "Algebra",
        "icon": "calculator",
        "color": "#3B82F6",
        "hours": 120,
        "level": "Foundation",
        "description": "Master the language of mathematics — variables, equations, and abstract reasoning.",
        "prerequisites": [],
        "units": [
            {"id": "alg_01", "name": "Foundations of Algebra", "topics": ["Real number system", "Order of operations", "Properties of equality", "Absolute value"], "hours": 8},
            {"id": "alg_02", "name": "Linear Equations & Inequalities", "topics": ["Solving linear equations", "Word problems", "Linear inequalities", "Compound inequalities"], "hours": 10},
            {"id": "alg_03", "name": "Functions & Relations", "topics": ["Domain & range", "Function notation", "Composition", "Inverse functions"], "hours": 12},
            {"id": "alg_04", "name": "Polynomials", "topics": ["Polynomial operations", "Factoring", "Polynomial division", "Remainder theorem"], "hours": 14},
            {"id": "alg_05", "name": "Rational Expressions", "topics": ["Simplifying", "Operations", "Complex fractions", "Rational equations"], "hours": 10},
            {"id": "alg_06", "name": "Radicals & Exponents", "topics": ["Rational exponents", "Radical expressions", "Radical equations", "Complex numbers intro"], "hours": 10},
            {"id": "alg_07", "name": "Quadratic Equations", "topics": ["Factoring", "Completing the square", "Quadratic formula", "Discriminant analysis"], "hours": 14},
            {"id": "alg_08", "name": "Systems of Equations", "topics": ["Substitution", "Elimination", "3-variable systems", "Matrix intro"], "hours": 12},
            {"id": "alg_09", "name": "Exponential & Logarithmic Functions", "topics": ["Exponential growth/decay", "Logarithmic properties", "Solving exp/log equations", "Applications"], "hours": 14},
            {"id": "alg_10", "name": "Sequences & Series", "topics": ["Arithmetic sequences", "Geometric sequences", "Sigma notation", "Binomial theorem"], "hours": 10},
            {"id": "alg_11", "name": "Conic Sections", "topics": ["Circles", "Parabolas", "Ellipses", "Hyperbolas"], "hours": 6},
        ],
        "applications": ["Game economy balancing", "Procedural generation formulas", "Physics simulation parameters", "AI behavior curves"],
        "game_dev_relevance": "Every game formula — from damage calculations to loot probability — is algebra."
    },
    "linear_algebra": {
        "id": "linear_algebra",
        "name": "Linear Algebra",
        "icon": "grid",
        "color": "#8B5CF6",
        "hours": 160,
        "level": "Intermediate",
        "description": "The mathematics of transformations, spaces, and the backbone of computer graphics.",
        "prerequisites": ["algebra"],
        "units": [
            {"id": "la_01", "name": "Vectors in R^n", "topics": ["Vector operations", "Dot product", "Cross product", "Vector spaces"], "hours": 12},
            {"id": "la_02", "name": "Matrices & Operations", "topics": ["Matrix arithmetic", "Transpose", "Symmetric matrices", "Block matrices"], "hours": 14},
            {"id": "la_03", "name": "Systems of Linear Equations", "topics": ["Gaussian elimination", "Row echelon form", "Reduced row echelon", "Rank & nullity"], "hours": 14},
            {"id": "la_04", "name": "Determinants", "topics": ["Cofactor expansion", "Properties", "Cramer's rule", "Geometric interpretation"], "hours": 10},
            {"id": "la_05", "name": "Vector Spaces", "topics": ["Subspaces", "Linear independence", "Basis & dimension", "Change of basis"], "hours": 16},
            {"id": "la_06", "name": "Linear Transformations", "topics": ["Kernel & image", "Matrix representation", "Composition", "Isomorphisms"], "hours": 16},
            {"id": "la_07", "name": "Eigenvalues & Eigenvectors", "topics": ["Characteristic polynomial", "Diagonalization", "Spectral theorem", "Jordan form intro"], "hours": 18},
            {"id": "la_08", "name": "Inner Product Spaces", "topics": ["Inner products", "Orthogonality", "Gram-Schmidt", "QR decomposition"], "hours": 14},
            {"id": "la_09", "name": "Singular Value Decomposition", "topics": ["SVD computation", "Low-rank approximation", "Pseudoinverse", "PCA connection"], "hours": 16},
            {"id": "la_10", "name": "Applications to Graphics", "topics": ["Homogeneous coordinates", "Model/View/Projection matrices", "Quaternions", "Skeletal animation math"], "hours": 20},
            {"id": "la_11", "name": "Applications to ML/AI", "topics": ["Covariance matrices", "PCA", "Neural network weight matrices", "Gradient computation"], "hours": 10},
        ],
        "applications": ["3D transformations", "Camera systems", "Shader math", "Physics engines", "ML/AI"],
        "game_dev_relevance": "Every vertex transformed, every camera moved, every physics collision — linear algebra."
    },
    "geometry": {
        "id": "geometry",
        "name": "Geometry",
        "icon": "shapes",
        "color": "#10B981",
        "hours": 100,
        "level": "Foundation",
        "description": "The study of shapes, space, and spatial reasoning — the visual heart of game development.",
        "prerequisites": [],
        "units": [
            {"id": "geo_01", "name": "Euclidean Foundations", "topics": ["Points, lines, planes", "Angles", "Parallel & perpendicular", "Axioms & postulates"], "hours": 8},
            {"id": "geo_02", "name": "Triangles", "topics": ["Congruence (SSS, SAS, ASA)", "Similarity", "Triangle inequality", "Pythagorean theorem"], "hours": 12},
            {"id": "geo_03", "name": "Polygons", "topics": ["Quadrilaterals", "Regular polygons", "Interior/exterior angles", "Tessellations"], "hours": 10},
            {"id": "geo_04", "name": "Circles", "topics": ["Arcs & chords", "Tangent lines", "Inscribed angles", "Power of a point"], "hours": 10},
            {"id": "geo_05", "name": "Area & Volume", "topics": ["2D areas", "Surface area", "Volumes of solids", "Cavalieri's principle"], "hours": 12},
            {"id": "geo_06", "name": "Coordinate Geometry", "topics": ["Distance formula", "Midpoint", "Slope", "Equations of lines & circles"], "hours": 10},
            {"id": "geo_07", "name": "Transformations", "topics": ["Translations", "Rotations", "Reflections", "Dilations & compositions"], "hours": 12},
            {"id": "geo_08", "name": "3D Geometry", "topics": ["3D coordinate systems", "Planes in 3D", "3D distance", "Euler's formula (V-E+F)"], "hours": 12},
            {"id": "geo_09", "name": "Computational Geometry", "topics": ["Convex hulls", "Voronoi diagrams", "Delaunay triangulation", "BSP trees"], "hours": 14},
        ],
        "applications": ["Level design", "Collision detection", "Mesh generation", "Pathfinding", "UI layout"],
        "game_dev_relevance": "Collision boxes, navmeshes, level layouts, procedural terrain — all geometry."
    },
    "precalculus": {
        "id": "precalculus",
        "name": "Pre-Calculus",
        "icon": "trending-up",
        "color": "#F59E0B",
        "hours": 100,
        "level": "Intermediate",
        "description": "Bridge the gap between algebra and calculus — trigonometry, functions, and limits.",
        "prerequisites": ["algebra", "geometry"],
        "units": [
            {"id": "pc_01", "name": "Trigonometric Functions", "topics": ["Unit circle", "Sine, cosine, tangent", "Reciprocal functions", "Graphs & transformations"], "hours": 14},
            {"id": "pc_02", "name": "Trigonometric Identities", "topics": ["Pythagorean identities", "Sum/difference formulas", "Double/half angle", "Product-to-sum"], "hours": 12},
            {"id": "pc_03", "name": "Inverse Trigonometric Functions", "topics": ["arcsin, arccos, arctan", "Compositions", "Solving trig equations", "Applications"], "hours": 10},
            {"id": "pc_04", "name": "Polar Coordinates", "topics": ["Polar/rectangular conversion", "Polar graphs", "Complex numbers in polar", "De Moivre's theorem"], "hours": 10},
            {"id": "pc_05", "name": "Vectors & Parametric Equations", "topics": ["2D & 3D vectors", "Parametric curves", "Projectile motion", "Cycloids"], "hours": 12},
            {"id": "pc_06", "name": "Limits & Continuity", "topics": ["Intuitive limits", "Limit laws", "Squeeze theorem", "Continuity"], "hours": 12},
            {"id": "pc_07", "name": "Advanced Functions", "topics": ["Polynomial long division", "Partial fractions", "Rational functions", "Asymptotes"], "hours": 10},
            {"id": "pc_08", "name": "Matrices & Determinants Review", "topics": ["2x2 and 3x3 systems", "Matrix operations", "Determinants", "Inverse matrices"], "hours": 8},
            {"id": "pc_09", "name": "Mathematical Induction", "topics": ["Weak induction", "Strong induction", "Well-ordering", "Proof techniques"], "hours": 8},
        ],
        "applications": ["Rotation systems", "Wave mechanics", "Projectile physics", "Signal processing"],
        "game_dev_relevance": "Trig drives every rotation, wave, and oscillation in games. Essential for physics and graphics."
    },
    "calculus": {
        "id": "calculus",
        "name": "Calculus",
        "icon": "pulse",
        "color": "#EF4444",
        "hours": 180,
        "level": "Advanced",
        "description": "The mathematics of change — derivatives, integrals, and the continuous world.",
        "prerequisites": ["precalculus"],
        "units": [
            {"id": "calc_01", "name": "Limits & Continuity", "topics": ["Epsilon-delta definition", "Limit theorems", "Continuity types", "Intermediate value theorem"], "hours": 14},
            {"id": "calc_02", "name": "Derivatives", "topics": ["Definition & interpretation", "Differentiation rules", "Chain rule", "Implicit differentiation"], "hours": 18},
            {"id": "calc_03", "name": "Applications of Derivatives", "topics": ["Related rates", "Optimization", "L'Hôpital's rule", "Newton's method"], "hours": 16},
            {"id": "calc_04", "name": "Curve Sketching", "topics": ["Critical points", "Inflection points", "Concavity", "Asymptotic behavior"], "hours": 10},
            {"id": "calc_05", "name": "Integration", "topics": ["Riemann sums", "Fundamental theorem", "Substitution", "Integration by parts"], "hours": 18},
            {"id": "calc_06", "name": "Applications of Integration", "topics": ["Area between curves", "Volumes of revolution", "Arc length", "Surface area"], "hours": 16},
            {"id": "calc_07", "name": "Techniques of Integration", "topics": ["Trig substitution", "Partial fractions", "Improper integrals", "Numerical methods"], "hours": 14},
            {"id": "calc_08", "name": "Sequences & Series", "topics": ["Convergence tests", "Power series", "Taylor series", "Maclaurin series"], "hours": 18},
            {"id": "calc_09", "name": "Differential Equations Intro", "topics": ["Separable ODEs", "First-order linear", "Euler's method", "Applications to physics"], "hours": 16},
            {"id": "calc_10", "name": "Parametric & Polar Calculus", "topics": ["Parametric derivatives", "Polar area", "Polar arc length", "Curvature"], "hours": 12},
        ],
        "applications": ["Physics simulation (velocity, acceleration)", "Fluid dynamics", "Optimization algorithms", "Animation curves", "Procedural generation"],
        "game_dev_relevance": "Velocity, acceleration, smooth interpolation, physics engines — calculus is the engine of motion."
    },
    "multivariable_calculus": {
        "id": "multivariable_calculus",
        "name": "Multivariable Calculus",
        "icon": "cube",
        "color": "#EC4899",
        "hours": 200,
        "level": "Expert",
        "description": "Calculus in multiple dimensions — the math of 3D worlds, fields, and flows.",
        "prerequisites": ["calculus", "linear_algebra"],
        "units": [
            {"id": "mv_01", "name": "Vectors & 3D Space", "topics": ["3D coordinates", "Vector-valued functions", "Space curves", "TNB frame"], "hours": 14},
            {"id": "mv_02", "name": "Partial Derivatives", "topics": ["Limits in R^n", "Partial derivatives", "Tangent planes", "Chain rule in R^n"], "hours": 16},
            {"id": "mv_03", "name": "Gradient & Directional Derivatives", "topics": ["Gradient vector", "Directional derivatives", "Level curves/surfaces", "Gradient descent"], "hours": 14},
            {"id": "mv_04", "name": "Optimization in R^n", "topics": ["Critical points", "Second derivative test", "Lagrange multipliers", "Constrained optimization"], "hours": 16},
            {"id": "mv_05", "name": "Multiple Integrals", "topics": ["Double integrals", "Triple integrals", "Change of variables", "Jacobian"], "hours": 18},
            {"id": "mv_06", "name": "Cylindrical & Spherical Coordinates", "topics": ["Cylindrical coordinates", "Spherical coordinates", "Integration in other coords", "Applications"], "hours": 12},
            {"id": "mv_07", "name": "Vector Fields", "topics": ["Vector field visualization", "Divergence", "Curl", "Conservative fields"], "hours": 16},
            {"id": "mv_08", "name": "Line & Surface Integrals", "topics": ["Line integrals", "Surface integrals", "Flux integrals", "Parametric surfaces"], "hours": 18},
            {"id": "mv_09", "name": "Fundamental Theorems", "topics": ["Green's theorem", "Stokes' theorem", "Divergence theorem", "Unified view"], "hours": 20},
            {"id": "mv_10", "name": "Applications to Game Dev", "topics": ["Fluid simulation", "Electromagnetic fields", "Terrain generation", "Neural network backprop"], "hours": 18},
        ],
        "applications": ["Fluid simulation", "Volumetric rendering", "Terrain heightmaps", "Global illumination", "Neural network training"],
        "game_dev_relevance": "3D fluid, smoke, volumetric clouds, global illumination — multivariable calculus powers AAA visuals."
    },
}

# Complete physics curriculum for Jeeves
PHYSICS_COURSES = {
    "classical_mechanics": {"id": "classical_mechanics", "name": "Classical Mechanics", "icon": "rocket", "color": "#3B82F6", "hours": 160, "units": ["Kinematics", "Newton's Laws", "Work & Energy", "Momentum", "Rotational Dynamics", "Gravitation", "Oscillations", "Fluid Mechanics"]},
    "electromagnetism": {"id": "electromagnetism", "name": "Electromagnetism", "icon": "flash", "color": "#F59E0B", "hours": 140, "units": ["Electrostatics", "Gauss's Law", "Electric Potential", "Capacitance", "Current & Resistance", "Magnetic Fields", "Faraday's Law", "Maxwell's Equations"]},
    "thermodynamics": {"id": "thermodynamics", "name": "Thermodynamics", "icon": "thermometer", "color": "#EF4444", "hours": 100, "units": ["Temperature & Heat", "Laws of Thermodynamics", "Entropy", "Heat Engines", "Statistical Mechanics Intro"]},
    "quantum_mechanics": {"id": "quantum_mechanics", "name": "Quantum Mechanics", "icon": "nuclear", "color": "#8B5CF6", "hours": 180, "units": ["Wave-Particle Duality", "Schrödinger Equation", "Operators & Observables", "Hydrogen Atom", "Angular Momentum", "Spin", "Perturbation Theory"]},
    "relativity": {"id": "relativity", "name": "Special & General Relativity", "icon": "planet", "color": "#EC4899", "hours": 120, "units": ["Lorentz Transformations", "Spacetime", "Mass-Energy", "General Relativity Intro", "Black Holes", "Gravitational Waves"]},
    "optics": {"id": "optics", "name": "Optics & Waves", "icon": "eye", "color": "#10B981", "hours": 80, "units": ["Geometric Optics", "Wave Optics", "Interference", "Diffraction", "Polarization", "Fiber Optics"]},
}

# Complete CS curriculum
CS_COURSES = {
    "data_structures": {"id": "data_structures", "name": "Data Structures", "icon": "git-network", "color": "#3B82F6", "hours": 120, "units": ["Arrays & Linked Lists", "Stacks & Queues", "Trees & BSTs", "Heaps", "Hash Tables", "Graphs", "Tries", "Advanced Structures"]},
    "algorithms": {"id": "algorithms", "name": "Algorithms", "icon": "code-working", "color": "#8B5CF6", "hours": 160, "units": ["Sorting", "Searching", "Graph Algorithms", "Dynamic Programming", "Greedy Algorithms", "Divide & Conquer", "NP-Completeness", "Approximation"]},
    "operating_systems": {"id": "operating_systems", "name": "Operating Systems", "icon": "desktop", "color": "#EF4444", "hours": 140, "units": ["Processes & Threads", "CPU Scheduling", "Memory Management", "Virtual Memory", "File Systems", "I/O Systems", "Deadlocks", "Security"]},
    "computer_graphics": {"id": "computer_graphics", "name": "Computer Graphics", "icon": "color-palette", "color": "#10B981", "hours": 200, "units": ["Rasterization", "Ray Tracing", "Shading Models", "Texture Mapping", "Global Illumination", "Real-Time Rendering", "GPU Architecture", "Vulkan/DirectX"]},
    "networking": {"id": "networking", "name": "Computer Networking", "icon": "wifi", "color": "#F59E0B", "hours": 100, "units": ["OSI Model", "TCP/IP", "HTTP/HTTPS", "DNS", "Sockets", "WebSockets", "NAT Traversal", "Game Networking"]},
    "compilers": {"id": "compilers", "name": "Compilers & Interpreters", "icon": "build", "color": "#EC4899", "hours": 140, "units": ["Lexical Analysis", "Parsing", "AST", "Semantic Analysis", "Code Generation", "Optimization", "JIT Compilation", "Garbage Collection"]},
    "ai_ml": {"id": "ai_ml", "name": "AI & Machine Learning", "icon": "hardware-chip", "color": "#6366F1", "hours": 200, "units": ["Supervised Learning", "Unsupervised Learning", "Neural Networks", "CNNs", "RNNs/Transformers", "Reinforcement Learning", "GANs", "Diffusion Models"]},
    "databases": {"id": "databases", "name": "Database Systems", "icon": "server", "color": "#14B8A6", "hours": 100, "units": ["Relational Model", "SQL", "Normalization", "Indexing", "Transactions", "NoSQL", "Distributed Databases", "Query Optimization"]},
}


@router.get("/courses")
async def get_all_math_courses():
    return {
        "math": {k: {"id": v["id"], "name": v["name"], "icon": v["icon"], "color": v["color"], "hours": v["hours"], "level": v["level"], "unit_count": len(v["units"]), "description": v["description"]} for k, v in MATH_COURSES.items()},
        "physics": {k: {"id": v["id"], "name": v["name"], "icon": v["icon"], "color": v["color"], "hours": v["hours"], "unit_count": len(v["units"])} for k, v in PHYSICS_COURSES.items()},
        "cs": {k: {"id": v["id"], "name": v["name"], "icon": v["icon"], "color": v["color"], "hours": v["hours"], "unit_count": len(v["units"])} for k, v in CS_COURSES.items()},
        "total_hours": sum(c["hours"] for c in MATH_COURSES.values()) + sum(c["hours"] for c in PHYSICS_COURSES.values()) + sum(c["hours"] for c in CS_COURSES.values()),
    }


@router.get("/math/{course_id}")
async def get_math_course(course_id: str):
    if course_id not in MATH_COURSES:
        return {"error": f"Math course '{course_id}' not found"}
    return MATH_COURSES[course_id]


@router.get("/math/{course_id}/unit/{unit_id}")
async def get_math_unit(course_id: str, unit_id: str):
    if course_id not in MATH_COURSES:
        return {"error": "Course not found"}
    course = MATH_COURSES[course_id]
    unit = next((u for u in course["units"] if u["id"] == unit_id), None)
    if not unit:
        return {"error": "Unit not found"}
    return {"course": course["name"], "unit": unit}


@router.get("/physics/{course_id}")
async def get_physics_course(course_id: str):
    if course_id not in PHYSICS_COURSES:
        return {"error": "Physics course not found"}
    return PHYSICS_COURSES[course_id]


@router.get("/cs/{course_id}")
async def get_cs_course(course_id: str):
    if course_id not in CS_COURSES:
        return {"error": "CS course not found"}
    return CS_COURSES[course_id]
