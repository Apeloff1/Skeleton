# Source-controlled full laptop API contract casebooks

26 independent boundaries × 14 literal source examples = 364 observed
execution expectations: 26 valid inputs, 327 required denials and 11 redaction
cases. Every case is stored as a named JSON record with an explicit expected
outcome, threat class, authority boundary and remaining operator evidence.

The runner reads bounded strict JSON and calls the actual laptop API Python
validators and state controls, *not* a mock inference engine. Supporting
loopback HTTP integration tests use a clearly labeled contract-only test
double solely to exercise framing and authorization.

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.cli
python -m unittest discover -s skeleton/testing -p 'test_laptop_qualification_*.py' -q
```

Do not replace a rejected case with an expected admission unless the current
production threat model and a focused independent review justify the change.
A source pass cannot certify real GGUF generation, licensing, cold restart,
GPU/memory pressure, the user's laptop, or exact-head release workflows.
