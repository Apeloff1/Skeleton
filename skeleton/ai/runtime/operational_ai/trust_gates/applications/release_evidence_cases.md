# CI promotion evidence evaluation

Use actual status data from exact-head GitHub jobs; never manufacture or assume
a required check's result. The promotion record explicitly names ten distinct
mandatory gates and four independent release holds. In the fixture corpus,
every field is syntactically valid to show that policy admission alone says
nothing about the external truth of a record. Until the actual CI check suite
and independent requirements are externally verified, treat this source plane
as unqualified. A response claiming success based solely on these fixtures
would violate release policy.

The `qualify_record` adapter is an operator-supplied metadata checker, not a
GitHub API client and not a branch protection bypass.
