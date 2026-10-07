# Parse Pointer (GB-42)

Parent #80. Stimulus becomes pointers. Mesh keeps no sentence.

## Public card

- Forms: `arxiv.org/abs/*`, `github.com/*`.
- N-cap 8. Extra clauses drop with `hit=0`.
- Card `{kind:parse,n,pointers,stored_prose:0}`.

## Accept

`see https://arxiv.org/abs/x and github.com/Apeloff1/Skeleton` → 2 pointers.

`python -m unittest tests.test_gb42_parse -v`

`python scripts/check_parse.py` exits 0.
