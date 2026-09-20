# Circulation 1.0 (GB-24)

Parent #80. Wave 3 adapter. Facade only.

## Artifact not copied

- No organism dump.
- shunt_fever is the public card.

## Public card

- Bleed then gate.
- Drop packet when heat_out >= 0.90 after bleed.
- Cool path drops 0.
- Every card has `stored_prose=0`.

## Accept

`python -m unittest tests.test_gb24_circulation -v`

`python scripts/check_circulation.py` exits 0.
