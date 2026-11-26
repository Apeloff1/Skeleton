"""Documented conservation bounds for the contact step.

Isolated pair, friction coefficient zero, restitution one
---------------------------------------------------------
The normal impulse is equal and opposite, and a central sphere collision does
not feed the tangential or spin terms. Linear momentum of the pair therefore
stays inside ``LINEAR_MOMENTUM_EPSILON_NS`` (newton-seconds). The bound is an
absolute residual on ``|m1 v1 + m2 v2|`` before versus after the step. It is
not a score: callers subtract the two momentum vectors.

Friction
--------
Coulomb friction uses the same geometric-mean coefficient as the reference
impulse solver, ``sqrt(mu_a * mu_b)``, and the friction impulse is clamped by
``mu * j_n`` and opposed to the tangential contact velocity. Mechanical energy,
including spherical spin ``0.4 m r^2``, therefore does not rise by more than
``ENERGY_INCREASE_EPSILON_J`` joules. A driven kinematic surface can do work;
the bound applies to an isolated pair and to a sphere against terrain whose
velocity is zero.

Multipoint segmented contacts
-----------------------------
Each contact impulse is applied at a point, but only the total force changes
linear momentum. The vector sum of those impulses matches ``m Δv`` of the
pose-aware center of mass inside ``IMPULSE_SUM_EPSILON_NS``.
"""

from __future__ import annotations

# Absolute newton-second residual for an isolated elastic frictionless pair.
LINEAR_MOMENTUM_EPSILON_NS = 1e-6

# Absolute joule excess allowed on top of the pre-step kinetic energy.
ENERGY_INCREASE_EPSILON_J = 1e-6

# Absolute newton-second residual between summed contact impulses and m Δv.
IMPULSE_SUM_EPSILON_NS = 1e-6
