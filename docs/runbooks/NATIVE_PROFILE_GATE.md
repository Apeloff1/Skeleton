# P2 native profile gate

Machine owner: `skeleton/native/profile_gate.py`.
AI-tree mirror: `skeleton/ai/runtime/native/profile_gate.py`.

The gate selects native or JVM acceleration only when a profile has enough samples, a matching ABI and protocol, and a proven speedup. Otherwise the scalar path remains the correctness owner. A native exception is isolated and the scalar path still returns.

No completion checkbox. No signatures. stored_prose=0. This does not promote P2-NATIVE-01.

```bash
python -m pytest -q skeleton/testing/test_native_profile_gate.py
```
