# Cooperative CPU principal capacity partition

The in-process CPU capacity guard now caps active reservations per verified
principal in addition to its global active, token, and byte budgets. A
single verified owner cannot consume every default slot; the default
per-principal limit is four of eight active reservations. Smaller configured
global limits automatically bound the effective per-principal maximum.

The same rule is enforced for both one-at-a-time reservations and atomic
fair-cycle proposals. A fair cycle that exceeds any principal's capacity
holds entirely without partially allocating resources. Principal identity
must be established by the caller's independent trusted verifier; arbitrary
user-supplied labels are not authorization. The partition is cooperative
and in-process only, not a multi-process resource guarantee or execution
lease. Unknown pressure, disk capacity, or checkpoint custody still holds.

Regression fixtures cover competing principals, atomic over-capacity
cycles, and preservation of unallocated slots for another verified owner.

Principal isolation also bounds aggregate reserved token windows and requested
memory bytes (defaults: 4,096 tokens and 32 MiB per verified principal),
not merely active slot count. This prevents a tenant from exhausting the
global token or byte budget with fewer than its allotted slots. Limits remain
in-process and observational; backend enforcement is still mandatory.
