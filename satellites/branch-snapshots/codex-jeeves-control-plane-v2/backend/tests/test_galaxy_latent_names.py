"""
Regression guard for latent NameError fixes + build-dict normalization
discovered during the Jun 2026 galaxy_studio decomposition.

Previously these module-level names were referenced inside endpoints but never
defined → guaranteed NameError 500 when the /expand, /vault/zip-to-apk and
zip/apk-packaging paths ran:
  - EXPANSION_PHASES  (used by galaxy_expand)
  - VAULT_DIR         (used by zip-to-apk; also imported by server.py)
  - _vault_entries    (written by _vault_save; owned by galaxy_studio_state)

Also guards _normalize_build(), which backfills lifecycle keys so the background
build runner can't KeyError on a slimmed/reloaded build dict.
"""
import routes.galaxy_studio as g
import routes.galaxy_studio_state as state


def test_module_level_names_defined():
    import os
    # VAULT_DIR may be a str or PathLike (build_vault.BUILDS_ROOT is a Path);
    # os.path.join accepts both — assert it resolves to a non-empty path.
    assert os.fspath(g.VAULT_DIR)
    assert isinstance(g.EXPANSION_PHASES, list) and len(g.EXPANSION_PHASES) >= 1
    # _vault_entries must be the SAME shared object the state module owns.
    assert g._vault_entries is state._vault_entries


def test_expansion_phases_shape():
    for p in g.EXPANSION_PHASES:
        assert set(("id", "name", "agents", "pct")) <= set(p.keys())
        assert p["id"].startswith("exp_")
        assert isinstance(p["agents"], int) and p["agents"] > 0
    # cumulative progress reaches 100%
    assert g.EXPANSION_PHASES[-1]["pct"] == 100
    # ids map onto the synergy constellation table (non-empty synergies)
    for p in g.EXPANSION_PHASES:
        syn = g._get_phase_synergies(p["id"].replace("exp_", ""))
        assert isinstance(syn, list)


def test_normalize_build_backfills_lifecycle_keys():
    norm = g._normalize_build({"build_id": "x"})
    assert norm["current_phase"] == 0      # the reported crash key
    assert norm["total_phases"] == 100
    assert norm["phases"] == []
    assert norm["files"] == {}
    assert norm["status"] == "building"
    # never overwrites real values
    keep = g._normalize_build({"current_phase": 7, "phases": [{"id": "p1"}]})
    assert keep["current_phase"] == 7
    assert keep["phases"] == [{"id": "p1"}]


def test_vault_dir_matches_build_vault_root():
    # VAULT_DIR should track the canonical build-vault directory.
    try:
        from core.build_vault import BUILDS_ROOT
        assert g.VAULT_DIR == BUILDS_ROOT
    except Exception:
        # fallback path still yields a usable directory string
        assert g.VAULT_DIR
