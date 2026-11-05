# Original combat delivery: playable package × acceptance

`python -m skeleton combat-delivery-accept demo` builds the original
Bridge Watch contract and checks the authored source, canonical turns,
earned credits/inventory, rights declaration, package manifest and portable
save against an independently replayed end-to-end acceptance receipt.

The `build`, `verify` and `play` commands reject mismatched source
digests, reward state, acceptance replay, manifest metadata and checksums.
No external executable, untrusted asset, or vendor content is executed.
The rights declaration is a claim by the publisher, **not** evidence of
ownership, authorization, provenance, marketplace acceptance or device
qualification. Release and exact-head security gates remain separate.
