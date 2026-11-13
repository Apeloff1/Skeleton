# Read-only installed original-game source reconciliation

A successful earlier installation does not prove that installed source still
matches the independently pinned delivery ZIP after a restart or disk recovery.

Run the integrated app CLI:

```sh
python -m skeleton app studio-journey --reconcile-install \
  --output /private/installed-original \
  --archive /private/delivery.zip \
  --expected-archive-sha256 <independent-archive-pin> \
  --expected-manifest-sha256 <independent-manifest-pin> \
  --trusted-local-operator
```

The command checks the canonical ZIP inventory, reads every installed source
file through descriptor-relative nofollow paths, compares all bytes to the
archive, reexecutes canonical original-game replay, then verifies the installed
tree and archive again. It does not write files, reserve a destination, install
packages, perform local AI inference, or run native Godot. The pins must come
from operator-controlled records outside the ZIP and installed source.

It is a point-in-time integrity receipt only; no device, content-rights,
signature, or consumer release qualification is claimed. All existing exact
head CI, security, CodeQL, malware, dependency, review and release holds remain.

Focused acceptance:
```sh
python -m pytest -q skeleton/testing/test_app_offline_install_reconciliation.py
```
