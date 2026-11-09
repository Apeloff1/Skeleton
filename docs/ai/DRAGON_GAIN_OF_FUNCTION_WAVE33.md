# Wave 33 — Articulated robotics and physics scene graph intelligence

The canonical Dragon crawler gains bounded, inert structural ingestion of
URDF robot models, Gazebo SDF models and MuJoCo MJCF body hierarchies.

Shared robot source XML admission rejects DTD/ENTITY, oversized/overdeep
element trees, nonfinite physical scalar values, unbounded metadata and
foreign root namespaces. Robots expose source-declared link and joint
counts, typed kinematic relationships, visual and collider summaries,
geometry reference counts and deterministic source hierarchy hashes.

URDF parent/child joint references are resolved only within the
already fetched document's local link namespace. Missing links, duplicate
joint identities, multiple parents and cyclic articulated structures
are rejected before source publication. Xacro includes, ROS, runtime
controllers, mesh resources and remote robot components cannot execute.

SDF recognizes bounded single-model link/joint topology and inertia
mass declarations. Includes and mesh paths are counted but never
dereferenced; physics, sensors and plugins are not activated.

MJCF reconstructs a finite nested body graph with counts of joints,
geometry, sites, cameras, lights, mesh asset declarations and includes,
without starting MuJoCo, opening plugin files or executing actuators.

All source observations are retained by the original CrawlRun only
under consent, robots, public destination, request/byte budget,
capture-rights and unreviewed evidence custody. Full structural
negative tests and actual scripted run_slice/replay assert zero
unapproved asset requests. This is source intelligence, not robotics
simulation or a certification of physical safety.
