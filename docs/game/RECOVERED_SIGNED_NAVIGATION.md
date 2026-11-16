# Recovered signed route / quest / GPS execution

The strict route adapter requires externally supplied HMAC authorizations
over exact route identity, waypoint order, direction, consumer permissions,
canonical quest plan digest and an exact authored-geometry catalogue digest.
It reuses the original RouteGrounder; legacy free-text note signatures
are not treated as strict geometry authorizations. An independent catalogue
pin and an environment-provided local key are required. The tool never
generates approvals, exports the key or changes the world.

The grounded-quest qualification replays actual canonical quest actions
through signed hop checks, projects fixed authored coordinates into the
existing FrameGPSHub and verifies every frame, including its proof hash,
lane and identity. It repeats the journey, checks the final canonical
save replay and retains source-bound receipts. GPS chain validation now
rejects metadata mismatch, nonmonotonic frames and mismatched lengths.
Projected geometry is not a device GPS reading, native engine capture
or independently measured movement. Signature verification authenticates
the provided local key domain only; key lifecycle and authority remain
external. Tests are selected but unexecuted in this change.
