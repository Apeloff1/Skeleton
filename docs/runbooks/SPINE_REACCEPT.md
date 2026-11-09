# P2 digest-stable reaccept

Machine owner: `skeleton/persistence/spine_reaccept.py`

A caller digest that does not match the delivery is refused before accept. A matching duplicate does not move the fence. Poison is not repaired.

```bash
python -m pytest -q skeleton/testing/test_spine_reaccept.py skeleton/testing/test_spine_masterplan.py
```
