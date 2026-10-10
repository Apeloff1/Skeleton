"""Actual Dragon native release behavior and fail-closed portfolio boundaries."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json

import pytest

from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_native_projects import NativeProject, digest
from skeleton.ai.webcrawler.dragon_native_production import (
    ArtifactReceipt, ProductionRequest, _path, capability_matrix,
    make_source_release, plan_production, publish_production,
    validate_native_source, verify_published_production, verify_source_release,
)
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project


def request(**changes):
    baseline = ProductionRequest(
        title="Original Dragon Moonrise", style="arcade_score_attack",
        targets=("game_boy",), original_work_attested=True,
    )
    return replace(baseline, **changes)


def project_for(request_value=None):
    item = request_value or request()
    candidate = digest([item.request_id, "game_boy", item.style, item.seed])
    return render_native_project(
        title=item.title, target_id="game_boy", style=item.style,
        candidate_id=candidate, mechanics=(Mechanic.MOVEMENT, Mechanic.EXPLORATION),
        authorized=True,
    )


def rezip(replacements: dict[str, bytes], source: bytes, *, extras=None):
    memory = BytesIO()
    with ZipFile(BytesIO(source)) as original, ZipFile(memory, "w", ZIP_DEFLATED) as target:
        for name in original.namelist():
            target.writestr(name, replacements.get(name, original.read(name)))
        for name, body in (extras or []):
            target.writestr(name, body)
    return memory.getvalue()


def test_capability_matrix_does_not_conflate_catalog_and_emitter():
    rows = {row["id"]: row for row in capability_matrix()}
    assert "game_boy" in rows
    assert rows["game_boy"]["native_source_emitter"]
    assert rows["game_boy"]["local_verified_rom_compiler"]
    assert rows["game_boy"]["supported_styles"]
    assert not rows["ps5"]["native_source_emitter"]
    assert not rows["ps5"]["supported_styles"]
    assert all(row["claims"].startswith("source-only") for row in rows.values())


@pytest.mark.parametrize("changes,exception", [
    ({"title": "A"}, ValueError),
    ({"original_work_attested": False}, PermissionError),
    ({"original_work_attested": 1}, PermissionError),
    ({"targets": ()}, ValueError),
    ({"targets": ("game_boy", "game_boy")}, ValueError),
    ({"targets": ("imaginary",)}, ValueError),
    ({"targets": ("game_boy",) * 17}, ValueError),
    ({"style": "copyrighted_original_game"}, ValueError),
    ({"rights_basis": "unverified"}, ValueError),
    ({"rights_basis": "documented_license"}, PermissionError),
    ({"rights_basis": "verified_public_domain"}, PermissionError),
    ({"rights_reference": "\n"}, ValueError),
    ({"rights_reference": "x" * 241}, ValueError),
    ({"seed": -1}, ValueError),
    ({"seed": True}, ValueError),
    ({"compile_roms": 1}, ValueError),
    ({"require_compiled": True}, ValueError),
    ({"max_portfolio_bytes": 0}, ValueError),
])
def test_attestation_identity_budgets_and_strict_types(changes, exception):
    with pytest.raises(exception):
        request(**changes).validate()


def test_request_id_order_independent_but_rights_and_build_bound():
    a = request(targets=("nes", "game_boy"))
    b = request(targets=("game_boy", "nes"))
    assert a.request_id == b.request_id
    assert a.request_id != replace(a, seed=2).request_id
    assert a.request_id != replace(a, compile_roms=True).request_id
    assert a.request_id != replace(a, rights_reference="new evidence").request_id


def test_preflight_blocks_licensed_sdk_unimplemented_and_wrong_styles():
    unavailable = plan_production(request(targets=("ps5", "atari_2600", "game_boy")))
    assert {x.target: x.state for x in unavailable} == {
        "ps5": "blocked", "atari_2600": "blocked", "game_boy": "source_ready",
    }
    failure = plan_production(request(style="turn_based_rpg"))
    assert failure[0].state == "blocked"
    assert not failure[0].compiler_available or failure[0].state == "blocked"
    compiled = plan_production(request(targets=("pc_windows",), compile_roms=True))
    assert compiled[0].state == "blocked"


def test_plan_is_read_only_and_dry_run_does_not_create_target(tmp_path):
    destination = tmp_path / "not-created"
    result = publish_production(request(), destination, authorized=True, dry_run=True)
    assert result["status"] == "planned"
    assert not destination.exists()
    assert result["targets"][0]["build_evidence"] == "none"


def test_unavailable_targets_stop_all_publication_before_any_files(tmp_path):
    destination = tmp_path / "not-created"
    result = publish_production(
        request(targets=("game_boy", "ps5")), destination, authorized=True,
    )
    assert result["status"] == "blocked"
    assert not destination.exists()
    assert not result["artifacts"]


def test_refuses_unauthorized_publication(tmp_path):
    with pytest.raises(PermissionError):
        publish_production(request(), tmp_path / "out", authorized=False)
    assert not (tmp_path / "out").exists()


def test_native_source_real_emitter_fingerprinted_and_immutable():
    generated = project_for()
    hashes = validate_native_source(generated)
    assert hashes["dragon-native-manifest.json"]
    assert hashes["README.md"]
    assert len(hashes) == len(generated.files)
    assert generated.digest == digest(generated.files)
    bad = replace(generated, digest="0" * 64)
    with pytest.raises(ValueError, match="fingerprint"):
        validate_native_source(bad)


@pytest.mark.parametrize("filename", [
    "../secret.txt", "/etc/passwd", "foo/../../private", "./readme",
    "foo//bar", "x\\x", "x\x00y", "x\nbad",
])
def test_no_unsafe_paths(filename):
    with pytest.raises(ValueError):
        _path(filename)


def test_inventory_budgets_reject_extra_paths_or_binary_content():
    native = project_for()
    changed = dict(native.files)
    changed["../../secret"] = "test"
    with pytest.raises(ValueError):
        validate_native_source(replace(native, files=changed, digest=digest(changed)))
    changed = dict(native.files)
    changed["src/evidence.txt"] = "x" * 410_000
    with pytest.raises(ValueError):
        validate_native_source(replace(native, files=changed, digest=digest(changed)))
    changed = dict(native.files)
    changed["src/evidence.txt"] = "secret\x00"
    with pytest.raises(ValueError):
        validate_native_source(replace(native, files=changed, digest=digest(changed)))


def test_deterministic_archive_real_homebrew_no_fake_rom():
    spec = request()
    generated = project_for(spec)
    raw1, receipt1 = make_source_release(generated, spec)
    raw2, receipt2 = make_source_release(generated, spec)
    assert raw1 == raw2
    assert receipt1 == receipt2
    assert receipt1.binary_sha256 is None
    assert receipt1.evidence == "source_generated"
    verified = verify_source_release(raw1)
    assert verified["target"] == "game_boy"
    assert verified["source_fingerprint"] == generated.digest
    assert verified["binary_member"] is None
    assert verified["rights_attestation"] == "operator_attested_unverified"
    assert "not a legal clearance" in verified["legal_claim"]


def test_archive_corruption_is_not_claimed_released():
    spec = request()
    content, _ = make_source_release(project_for(spec), spec)
    with ZipFile(BytesIO(content)) as archive:
        first_name = next(n for n in archive.namelist() if n.startswith("source/"))
    malformed = rezip({first_name: b"replaced"}, content)
    with pytest.raises(ValueError, match="modified"):
        verify_source_release(malformed)
    malformed = rezip({}, content, extras=[("../attack", b"bad")])
    with pytest.raises(ValueError, match="unexpected"):
        verify_source_release(malformed)
    malformed = rezip({}, content, extras=[("release-receipt.json", b"{}")])
    with pytest.raises(ValueError, match="duplicate"):
        verify_source_release(malformed)


def test_binary_must_be_structurally_verified_not_self_asserted():
    spec = request()
    with pytest.raises(ValueError):
        make_source_release(project_for(spec), spec, binary=b"fake ROM",
                            compiler_state="compiled_native")
    with pytest.raises(ValueError):
        make_source_release(project_for(spec), spec, binary=b"fake ROM",
                            compiler_state="not_requested")
    with pytest.raises(RuntimeError):
        make_source_release(project_for(spec),
                            replace(spec, compile_roms=True, require_compiled=True))


def test_publish_validate_replay_verify_and_no_overwrite(tmp_path):
    output = tmp_path / "releases"
    first = publish_production(request(), output, authorized=True)
    assert first["status"] == "published"
    assert len(first["artifacts"]) == 1
    report = verify_published_production(output, first["index"])
    assert report["status"] == "verified"
    assert report["archives_verified"] == 1
    second = publish_production(request(), output, authorized=True)
    assert second["index_sha256"] == first["index_sha256"]
    assert second["artifacts"] == first["artifacts"]
    archive = output / first["artifacts"][0]["archive_name"]
    archive.write_bytes(archive.read_bytes() + b"malicious tail")
    with pytest.raises(ValueError, match="changed"):
        verify_published_production(output, first["index"])
    with pytest.raises(FileExistsError, match="conflicting"):
        publish_production(request(), output, authorized=True)


def test_portfolio_multiple_real_native_platforms(tmp_path):
    spec = request(targets=("nes", "game_boy"))
    result = publish_production(spec, tmp_path / "multi", authorized=True)
    assert result["status"] == "published"
    assert [x["target"] for x in result["artifacts"]] == ["game_boy", "nes"]
    assert all(x["evidence"] == "source_generated" for x in result["artifacts"])
    audit = verify_published_production(tmp_path / "multi", result["index"])
    assert audit["archives_verified"] == 2


def test_portfolio_refuses_symlink_root(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        publish_production(request(), link, authorized=True)
    assert list(actual.iterdir()) == []


def test_index_scope_is_not_hardware_gameplay_or_legal_certification(tmp_path):
    result = publish_production(request(), tmp_path, authorized=True)
    index = json.loads((tmp_path / result["index"]).read_text())
    assert index["production_evidence"] == "source_only"
    assert "external legal verification not asserted" in index["legal_claim"]
    audit = verify_published_production(tmp_path, result["index"])
    assert "not hardware or legal certification" in audit["scope"]


def test_missing_release_fails_offline_audit(tmp_path):
    result = publish_production(request(), tmp_path, authorized=True)
    (tmp_path / result["artifacts"][0]["archive_name"]).unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_published_production(tmp_path, result["index"])


def test_archive_source_fingerprint_attacks_are_detected():
    spec = request()
    raw, _ = make_source_release(project_for(spec), spec)
    with ZipFile(BytesIO(raw)) as archive:
        receipt = json.loads(archive.read("release-receipt.json"))
    receipt["source_fingerprint"] = "f" * 64
    modified = rezip({"release-receipt.json": json.dumps(receipt).encode()}, raw)
    with pytest.raises(ValueError, match="fingerprint"):
        verify_source_release(modified)


def test_archive_native_manifest_must_match_release_claim():
    spec = request()
    raw, _ = make_source_release(project_for(spec), spec)
    with ZipFile(BytesIO(raw)) as archive:
        receipt = json.loads(archive.read("release-receipt.json"))
        native = json.loads(archive.read("source/dragon-native-manifest.json"))
    native["target"] = "ps5"
    payload = (json.dumps(native, sort_keys=True, indent=2) + "\n").encode()
    receipt["source_files"]["dragon-native-manifest.json"] = __import__("hashlib").sha256(payload).hexdigest()
    # The source fingerprint is recomputed from every member, not merely a file-hash table.
    modified = rezip({
        "source/dragon-native-manifest.json": payload,
        "release-receipt.json": json.dumps(receipt).encode(),
    }, raw)
    with pytest.raises(ValueError, match="fingerprint"):
        verify_source_release(modified)


def test_existing_symlinked_archive_is_not_overwritten(tmp_path):
    spec = request()
    published = publish_production(spec, tmp_path, authorized=True)
    name = published["artifacts"][0]["archive_name"]
    outside = tmp_path.parent / "outside-not-touched.txt"
    outside.write_text("sensitive")
    (tmp_path / name).unlink()
    (tmp_path / name).symlink_to(outside)
    with pytest.raises((ValueError, FileExistsError)):
        publish_production(spec, tmp_path, authorized=True)
    assert outside.read_text() == "sensitive"


def test_invalid_index_filename_and_modification_fails(tmp_path):
    result = publish_production(request(), tmp_path, authorized=True)
    with pytest.raises(ValueError, match="index filename"):
        verify_published_production(tmp_path, "dragon-not-index.json")
    index_file = tmp_path / result["index"]
    document = json.loads(index_file.read_text())
    document["entries"][0]["archive_sha256"] = "f" * 64
    index_file.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        verify_published_production(tmp_path, result["index"])


def test_portfolio_budget_denied_before_file_writes(tmp_path):
    tiny = request(max_portfolio_bytes=1024)
    with pytest.raises(ValueError, match="budget"):
        publish_production(tiny, tmp_path / "not-created", authorized=True)
    assert not (tmp_path / "not-created").exists()


def test_existing_native_cli_portfolio_entrypoint(tmp_path, monkeypatch, capsys):
    from skeleton.ai.webcrawler.dragon_native_cli import main
    import sys
    args = [
        "dragon_native_cli", "--portfolio-targets", "game_boy,nes",
        "--title", "Original Moonrise", "--style", "arcade_score_attack",
        "--out", str(tmp_path), "--attest-original-rights",
        "--authorize-publication",
    ]
    monkeypatch.setattr(sys, "argv", args)
    main()
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "published"
    assert {row["target"] for row in output["artifacts"]} == {"game_boy", "nes"}
    assert verify_published_production(tmp_path, output["index"])["archives_verified"] == 2


def test_existing_cli_rejects_portfolio_only_flags(tmp_path, monkeypatch):
    from skeleton.ai.webcrawler.dragon_native_cli import main
    import sys
    monkeypatch.setattr(sys, "argv", [
        "dragon_native_cli", "--out", str(tmp_path), "--compile-roms"
    ])
    with pytest.raises(SystemExit) as exception:
        main()
    assert exception.value.code == 2
    assert not list(tmp_path.iterdir())


def test_product_is_still_source_not_fabricated_console_binary(tmp_path):
    output = publish_production(
        request(targets=("game_boy", "nes")), tmp_path, authorized=True
    )
    for row in output["artifacts"]:
        blob = (tmp_path / row["archive_name"]).read_bytes()
        with ZipFile(BytesIO(blob)) as packaged:
            assert not any(x.startswith("binary/") for x in packaged.namelist())
            assert packaged.read("release-receipt.json")
    assert output["status"] == "published"


def test_portfolio_discloses_actual_mode_differences(tmp_path):
    spec = request(targets=("game_boy", "pc_linux"))
    created = publish_production(spec, tmp_path, authorized=True)
    assert created["status"] == "published"
    info = json.loads((tmp_path / created["index"]).read_text())
    assert info["cross_target_fidelity"] == "different_implemented_modes_not_an_equivalent_port"
    assert len(info["declared_gameplay_modes"]) >= 2
    assert {entry["gameplay_mode"] for entry in info["entries"]} == set(info["declared_gameplay_modes"])
    assert verify_published_production(tmp_path, created["index"])["status"] == "verified"


def test_generated_source_budget_recomputed_not_just_declared():
    native = project_for()
    altered = dict(native.files)
    budget = json.loads(altered["dragon-hardware-budget.json"])
    budget["source_bytes"] = 1
    altered["dragon-hardware-budget.json"] = json.dumps(budget) + "\n"
    modified = replace(native, files=altered, digest=digest(altered))
    with pytest.raises(ValueError, match="hardware budget"):
        validate_native_source(modified)


def test_modified_source_with_forged_hash_table_rejected():
    spec = request()
    raw, _ = make_source_release(project_for(spec), spec)
    with ZipFile(BytesIO(raw)) as zipped:
        receipt = json.loads(zipped.read("release-receipt.json"))
        native = zipped.read("source/dragon-native-manifest.json")
    mutated = native.replace(b"source_generated", b"source_replaced")
    receipt["source_files"]["dragon-native-manifest.json"] = __import__("hashlib").sha256(mutated).hexdigest()
    modified = rezip({
        "source/dragon-native-manifest.json": mutated,
        "release-receipt.json": json.dumps(receipt).encode(),
    }, raw)
    with pytest.raises(ValueError, match="fingerprint"):
        verify_source_release(modified)



def test_memory_only_app_bundle_compiles_no_rom_and_writes_no_files(tmp_path, monkeypatch):
    from skeleton.ai.webcrawler.dragon_native_production import (
        build_source_bundle, verify_source_bundle,
    )
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    spec = request(targets=("game_boy", "nes"), max_portfolio_bytes=3_000_000)
    blob1, idx1 = build_source_bundle(spec, authorized=True)
    blob2, idx2 = build_source_bundle(spec, authorized=True)
    assert blob1 == blob2 and idx1 == idx2
    assert set(tmp_path.iterdir()) == before
    assert idx1["production_evidence"] == "source_only"
    assert verify_source_bundle(blob1)["target_count"] == 2
    with ZipFile(BytesIO(blob1)) as files:
        assert "production-index.json" in files.namelist()
        assert len(files.namelist()) == 3


def test_memory_bundle_rejects_compilation_and_excessive_targets():
    from skeleton.ai.webcrawler.dragon_native_production import build_source_bundle
    with pytest.raises(PermissionError):
        build_source_bundle(request(), authorized=False)
    with pytest.raises(PermissionError):
        build_source_bundle(request(compile_roms=True), authorized=True)
    with pytest.raises(ValueError):
        build_source_bundle(request(targets=("game_boy", "nes", "pc_linux", "pc_macos"),
                                    max_portfolio_bytes=3_000_000), authorized=True)


def test_memory_bundle_detects_adversarial_nested_mutation():
    from skeleton.ai.webcrawler.dragon_native_production import (
        build_source_bundle, verify_source_bundle,
    )
    raw, _ = build_source_bundle(request(max_portfolio_bytes=3_000_000),
                                 authorized=True)
    with ZipFile(BytesIO(raw)) as original:
        inner = next(n for n in original.namelist() if n.startswith("releases/"))
    compromised = rezip({inner: b"modified nested source"}, raw)
    with pytest.raises(ValueError, match="tampered"):
        verify_source_bundle(compromised)
    compromised = rezip({}, raw, extras=[("releases/alien.zip", b"x")])
    with pytest.raises(ValueError, match="unrecognized"):
        verify_source_bundle(compromised)



def test_license_reference_is_not_published_as_plaintext():
    spec = request(
        rights_basis="documented_license",
        rights_reference="private-license-reference-ALWAYS-OPAQUE",
    )
    payload, _ = make_source_release(project_for(spec), spec)
    receipt = verify_source_release(payload)
    assert "rights_reference" not in receipt
    assert receipt["rights_reference_sha256"] == __import__("hashlib").sha256(
        spec.rights_reference.encode()
    ).hexdigest()
    assert "private-license-reference" not in json.dumps(receipt)


def test_source_bundle_verifier_rejects_fake_compiled_claim():
    from skeleton.ai.webcrawler.dragon_native_production import (
        build_source_bundle, verify_source_bundle,
    )
    spec = request(max_portfolio_bytes=3_000_000)
    data, _ = build_source_bundle(spec, authorized=True)
    with ZipFile(BytesIO(data)) as outer:
        filename = next(n for n in outer.namelist() if n.startswith("releases/"))
        inner = outer.read(filename)
    with ZipFile(BytesIO(inner)) as native:
        receipt = json.loads(native.read("release-receipt.json"))
    receipt["compiler_state"] = "compiled_native"
    altered_inner = rezip(
        {"release-receipt.json": json.dumps(receipt).encode()}, inner,
    )
    altered_outer = rezip({filename: altered_inner}, data)
    with pytest.raises(ValueError):
        verify_source_bundle(altered_outer)


def test_creator_publisher_rejects_symlink_parent_before_writing(tmp_path):
    base = tmp_path / "actual"
    base.mkdir()
    shadow = tmp_path / "linked"
    shadow.symlink_to(base, target_is_directory=True)
    path = shadow / "release"
    with pytest.raises(ValueError, match="symlink"):
        publish_production(request(), path, authorized=True)
    assert not (base / "release").exists()



@pytest.mark.parametrize("field,altered", [
    ("production_evidence", "hardware_certified"),
    ("cross_target_fidelity", "equivalent_original_gameplay_across_platforms"),
    ("declared_gameplay_modes", ["invented_gameplay"]),
    ("legal_claim", "fully legally licensed and cleared"),
])
def test_release_audit_independently_reconstructs_top_level_claims(
    tmp_path, field, altered,
):
    out = tmp_path / "issued"
    result = publish_production(
        request(targets=("game_boy", "pc_linux")), out, authorized=True)
    index = out / result["index"]
    manifest = json.loads(index.read_text())
    manifest[field] = altered
    index.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="claims|claim|mode|legal|parity|level"):
        verify_published_production(out, result["index"])


@pytest.mark.parametrize("field,altered", [
    ("production_evidence", "console_certified"),
    ("cross_target_fidelity", "equivalent_port"),
    ("declared_gameplay_modes", ["fictitious"]),
    ("legal_claim", "licensed without review"),
])
def test_nested_browser_source_bundle_does_not_trust_index_claims(field, altered):
    from skeleton.ai.webcrawler.dragon_native_production import (
        build_source_bundle, verify_source_bundle,
    )
    spec = request(targets=("game_boy", "pc_linux"),
                   max_portfolio_bytes=3_000_000)
    payload, _ = build_source_bundle(spec, authorized=True)
    with ZipFile(BytesIO(payload)) as archive:
        index = json.loads(archive.read("production-index.json"))
    index[field] = altered
    forged = rezip({"production-index.json": json.dumps(index).encode()}, payload)
    with pytest.raises(ValueError, match="claims|claim|mode|legal|parity|level"):
        verify_source_bundle(forged)


def test_index_member_cannot_misstate_archive_evidence_or_gameplay(tmp_path):
    destination = tmp_path / "issued"
    result = publish_production(request(), destination, authorized=True)
    index = destination / result["index"]
    record = json.loads(index.read_text())
    record["entries"][0]["gameplay_mode"] = "different_game"
    index.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="gameplay_mode|disagree"):
        verify_published_production(destination, result["index"])


def test_index_path_and_request_prefix_bound(tmp_path):
    result = publish_production(request(), tmp_path, authorized=True)
    original = tmp_path / result["index"]
    substitute = tmp_path / ("dragon-production-" + "f" * 20 + ".json")
    substitute.write_bytes(original.read_bytes())
    with pytest.raises(ValueError, match="index name"):
        verify_published_production(tmp_path, substitute.name)



def test_portable_native_design_converts_to_real_target_specific_game_source(tmp_path):
    from skeleton.ai.webcrawler.dragon_native_production import (
        PortableGameDesign, _adapt_portable_design,
    )
    profile = PortableGameDesign(
        palette="modern_neon", hero="robot", quest_theme="space",
        difficulty=7, stages=6, candidates=12,
    )
    spec = request(targets=("game_boy", "pc_linux"), seed=981,
                   portable_design=profile)
    cartridge, degraded = _adapt_portable_design(spec, "game_boy")
    desktop, native = _adapt_portable_design(spec, "pc_linux")
    assert cartridge.seed == desktop.seed == 981
    assert cartridge.title == desktop.title == spec.title
    assert cartridge.hero == desktop.hero == "robot"
    assert cartridge.quest_theme == desktop.quest_theme == "space"
    assert cartridge.palette == "handheld"
    assert cartridge.stages == cartridge.candidates == 1
    assert desktop.palette == "modern_neon"
    assert desktop.stages == 6 and desktop.candidates == 12
    assert desktop.difficulty == cartridge.difficulty == 7
    assert "palette_adapted_to_cartridge_safe_class" in degraded["port_adjustments"]
    assert "hero_theme_and_difficulty_not_runtime_applied_by_cartridge_emitter" in degraded["port_adjustments"]
    assert not native["port_adjustments"]

    produced = publish_production(spec, tmp_path, authorized=True)
    assert produced["status"] == "published"
    assert len(produced["artifacts"]) == 2
    assert all(x["port_profile_digest"] for x in produced["artifacts"])
    assert verify_published_production(tmp_path, produced["index"])["archives_verified"] == 2
    for entry in produced["artifacts"]:
        receipt = verify_source_release((tmp_path / entry["archive_name"]).read_bytes())
        plan = receipt["port_plan"]
        assert plan["production_seed"] == 981
        assert plan["production_title"] == spec.title
        assert plan["portable_profile_digest"] == entry["port_profile_digest"]
        assert plan["target"] == entry["target"]


def test_portable_profile_revisions_materially_change_native_sources(tmp_path):
    from skeleton.ai.webcrawler.dragon_native_production import PortableGameDesign
    base = PortableGameDesign(palette="modern_neon", hero="robot", stages=5)
    next_profile = replace(base, hero="astronaut", stages=7, difficulty=9)
    first = request(targets=("pc_linux",), portable_design=base)
    next_spec = request(targets=("pc_linux",), portable_design=next_profile)
    assert first.request_id != next_spec.request_id
    a = publish_production(first, tmp_path / "a", authorized=True)
    b = publish_production(next_spec, tmp_path / "b", authorized=True)
    assert a["artifacts"][0]["source_fingerprint"] != b["artifacts"][0]["source_fingerprint"]
    assert a["artifacts"][0]["port_profile_digest"] != b["artifacts"][0]["port_profile_digest"]


@pytest.mark.parametrize("changes", [
    {"palette": "commercial_console_palette"},
    {"hero": "third_party_character"},
    {"quest_theme": "../../payload"},
    {"stages": 9},
    {"stages": True},
    {"candidates": 25},
    {"difficulty": 0},
    {"project_notes": "$(command)"},
    {"project_notes": "x" * 201},
])
def test_portable_design_rejects_unsupported_or_executable_inputs(changes):
    from skeleton.ai.webcrawler.dragon_native_production import PortableGameDesign
    with pytest.raises(ValueError):
        PortableGameDesign(**changes).validate()


def test_portable_design_source_bundle_survives_nested_evidence_replay():
    from skeleton.ai.webcrawler.dragon_native_production import (
        PortableGameDesign, build_source_bundle, verify_source_bundle,
    )
    spec = request(
        targets=("game_boy", "pc_linux"), seed=1337,
        max_portfolio_bytes=3_000_000,
        portable_design=PortableGameDesign(
            palette="modern_neon", hero="pilot", quest_theme="ice",
            difficulty=8, stages=5, candidates=6,
        ),
    )
    binary, index = build_source_bundle(spec, authorized=True)
    assert verify_source_bundle(binary)["status"] == "verified_source_bundle"
    assert index["target_count"] == 2
    assert all(item["port_profile_digest"] for item in index["entries"])
    with ZipFile(BytesIO(binary)) as outer:
        for name in outer.namelist():
            if name.startswith("releases/"):
                receipt = verify_source_release(outer.read(name))
                assert receipt["port_plan"]["claims"].endswith("gameplay certification")


def test_forged_cartridge_port_downgrade_detected_without_modifying_source():
    from skeleton.ai.webcrawler.dragon_native_production import (
        PortableGameDesign, build_source_bundle,
    )
    spec = request(max_portfolio_bytes=3_000_000, seed=42,
                   portable_design=PortableGameDesign(
                       stages=7, palette="modern_neon"))
    outer, _ = build_source_bundle(spec, authorized=True)
    with ZipFile(BytesIO(outer)) as archive:
        filename = next(name for name in archive.namelist() if name.startswith("releases/"))
        inner = archive.read(filename)
    with ZipFile(BytesIO(inner)) as native:
        receipt = json.loads(native.read("release-receipt.json"))
    receipt["port_plan"]["port_adjustments"] = []
    modified = rezip({"release-receipt.json": json.dumps(receipt).encode()}, inner)
    with pytest.raises(ValueError, match="portable game port evidence"):
        verify_source_release(modified)


def test_portable_request_never_accepts_untyped_arbitrary_profile():
    with pytest.raises(ValueError, match="typed portable"):
        request(portable_design={"stage": 200}).validate()



def test_verified_native_release_comparison_guides_real_revision_review(tmp_path):
    from skeleton.ai.webcrawler.dragon_native_production import (
        PortableGameDesign, compare_verified_portfolios,
    )
    first = request(
        targets=("game_boy", "pc_linux"),
        portable_design=PortableGameDesign(hero="hatchling", stages=4),
    )
    second = request(
        targets=("game_boy", "pc_linux"),
        portable_design=PortableGameDesign(hero="robot", stages=6),
    )
    previous = tmp_path / "previous"
    current = tmp_path / "current"
    a = publish_production(first, previous, authorized=True)
    b = publish_production(second, current, authorized=True)
    result = compare_verified_portfolios(previous, a["index"], current, b["index"])
    assert result["previous_request_id"] == first.request_id
    assert result["current_request_id"] == second.request_id
    assert result["changes"] >= 1
    assert result["previous_verified"] == result["current_verified"] == 2
    assert any("portable_game_design_changed" in x["causes_to_review"]
               for x in result["targets"])
    assert all(x["requires_new_compile_review"] for x in result["targets"]
               if x["state"] == "source_changed")
    assert "no automatic" in result["claim_boundary"]

    replay = compare_verified_portfolios(current, b["index"], current, b["index"])
    assert replay["changes"] == 0
    assert replay["unchanged"] == 2
    assert all(x["state"] == "identical" for x in replay["targets"])


def test_release_comparison_refuses_tampered_source_before_claiming_differences(tmp_path):
    from skeleton.ai.webcrawler.dragon_native_production import compare_verified_portfolios
    before = tmp_path / "before"
    after = tmp_path / "after"
    first = publish_production(request(), before, authorized=True)
    second = publish_production(request(seed=2), after, authorized=True)
    name = second["artifacts"][0]["archive_name"]
    (after / name).write_bytes(b"not a valid homebrew artifact")
    with pytest.raises(ValueError, match="changed"):
        compare_verified_portfolios(before, first["index"], after, second["index"])


def test_read_only_preflight_preview_exposes_actual_console_feature_downgrades():
    from skeleton.ai.webcrawler.dragon_native_production import (
        PortableGameDesign, preview_native_portfolio,
    )
    spec = request(
        targets=("game_boy", "ps5", "pc_linux"),
        portable_design=PortableGameDesign(stages=7, candidates=11,
                                           palette="modern_neon"),
    )
    report = preview_native_portfolio(spec)
    assert not report["can_export_sources"]
    assert report["status"] == "blocked"
    assert report["evidence"] == "none"
    targets = {item["target"]: item for item in report["targets"]}
    assert targets["ps5"]["state"] == "blocked"
    assert targets["ps5"]["target_design_digest"] is None
    assert targets["game_boy"]["state"] == "source_ready"
    assert targets["game_boy"]["target_stages"] == 1
    assert targets["game_boy"]["target_candidates"] == 1
    assert targets["game_boy"]["target_palette"] == "handheld"
    assert "palette_adapted_to_cartridge_safe_class" in targets["game_boy"]["adaptations"]
    assert targets["pc_linux"]["target_stages"] == 7
    assert targets["pc_linux"]["target_candidates"] == 11


def test_source_preview_never_builds_native_source_or_mints_completion(monkeypatch):
    from skeleton.ai.webcrawler import dragon_native_production as production
    def forbidden(**kwargs):
        raise AssertionError("preflight must not invoke native game emitters")
    monkeypatch.setattr(production, "render_native_project", forbidden)
    report = production.preview_native_portfolio(
        request(targets=("nes", "game_boy")),
    )
    assert report["can_export_sources"]
    assert report["evidence"] == "none"
    assert len(report["targets"]) == 2
