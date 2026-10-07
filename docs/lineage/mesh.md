# Mesh scan (GB-43)

Parent #80. Additive. Does not edit `split`.

## Public card

- Sentence-shaped strings increment `hits`.
- The card does not keep the sentence.
- `doctor=1` when hits > 0.

## Accept

`python -m unittest tests.test_gb43_mesh -v`

`python scripts/check_mesh.py` exits 0.
