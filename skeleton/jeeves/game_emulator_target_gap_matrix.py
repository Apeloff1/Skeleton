"""Honest 169-target emulator installation, controller and capability gap matrix.

No claimed hardware fidelity is derived from a platform name, a build recipe
or a static core-target mapping. Uses current operator registry inspection and
the canonical Dragon inventory. Reports next actions per target, without
downloading or executing games.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .game_comparison_controllers import controller_layout_for_target
from .game_comparison_schema import digest
from .game_emulator_catalog import GameEmulatorRegistry, canonical_targets

SCHEMA = "skeleton.game.emulator_target_qualification_matrix.v1"


def _core_actions(
    core: dict[str, Any], target_id: str, recipe: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """Operator guidance only: argv is displayed, never automatically dispatched."""
    identity = core["core_id"]
    code = core["readiness"]["code"]
    inspect = {
        "code": "inspect_installed_core",
        "message": "Inspect exact local ABI, library identity, approval and firmware without executing a core",
        "argv": [
            "python",
            "scripts/install_game_emulator_cores.py",
            "--installed-audit",
            "--install-root",
            "<operator-install-root>",
        ],
    }
    if core["available"]:
        actions = [
            {
                "code": "qualify_lawful_content",
                "message": "Run bounded actual replay qualification on your explicit lawful source; no fidelity or learning claim is implied",
                "argv": [
                    "python",
                    "scripts/qualify_game_emulator.py",
                    "--registry",
                    "<approved-cores.json>",
                    "--target",
                    target_id,
                    "--core",
                    identity,
                    "--source",
                    "<lawful-ROM>",
                    "--action",
                    "idle",
                    "--runs",
                    "2",
                ],
            },
            {
                "code": "qualify_lawful_multifile_content",
                "message": "Use a complete exact local disc/data tree rather than truncating it to the inline upload limit",
                "argv": [
                    "python",
                    "scripts/qualify_game_emulator.py",
                    "--registry",
                    "<approved-cores.json>",
                    "--target",
                    target_id,
                    "--core",
                    identity,
                    "--content-root",
                    "<lawful-content-directory>",
                    "--entrypoint",
                    "<relative-entrypoint>",
                    "--action",
                    "idle",
                    "--runs",
                    "2",
                ],
            },
        ]
    elif core["installation_present"] or code == "core_target_not_approved":
        if code in {
            "required_firmware_missing",
            "firmware_directory_unavailable",
            "firmware_identity_changed",
        }:
            message = "Install only your lawfully obtained declared firmware into the operator system directory, inspect it and explicitly reapprove the exact configuration"
            action = "supply_and_review_firmware"
        elif code in {"core_not_approved", "core_target_not_approved"}:
            message = "Review the recorded deferred core or target scope, firmware and runtime limitations before explicit operator approval"
            action = "review_operator_approval"
        elif code in {"core_identity_changed", "installation_changed", "core_authority_changed"}:
            message = "Preserve the old receipt; restore the exact approved installation or independently review and explicitly approve the replacement"
            action = "repair_changed_installation"
        elif code in {
            "unsupported_architecture",
            "architecture_mismatch",
            "missing_libretro_abi",
            "invalid_library",
            "unsupported_library",
        }:
            message = "Build a matching host-architecture libretro ABI from the pinned source; the existing binary cannot be activated"
            action = "repair_host_abi"
        else:
            message = "Repair the reported local installation permissions, path, byte or inventory problem before reinspection; never bypass the sandbox"
            action = "repair_local_installation"
        actions = [{"code": action, "message": message, "argv": []}, inspect]
    elif recipe is not None:
        actions = [
            {
                "code": "build_pinned_local_source",
                "message": "Build only an already present exact pinned source cache; fetching public source requires separately adding --fetch-sources",
                "argv": [
                    "python",
                    "scripts/install_game_emulator_cores.py",
                    "--source-root",
                    "<operator-source-cache>",
                    "--install-root",
                    "<operator-install-root>",
                    "--core",
                    identity,
                    "--jobs",
                    "1",
                    "--timeout",
                    "600",
                ],
            }
        ]
        if recipe.get("candidate_only"):
            actions.append(
                {
                    "code": "review_candidate_limitations",
                    "message": "This pinned recipe remains candidate-only after compilation; review its declared runtime/firmware limits before any explicit approval",
                    "argv": [],
                }
            )
    else:
        actions = [
            {
                "code": "implement_reviewed_build_recipe",
                "message": "No pinned installer recipe exists for this mapped core; supply a reviewed exact local installation or implement and declare its source recipe",
                "argv": [],
            }
        ]
    return [dict(action, automatic=False, operator_only=True) for action in actions]


def build_emulator_target_gap_matrix(*, registry: GameEmulatorRegistry | None = None) -> dict[str, Any]:
    from scripts.install_game_emulator_cores import PINNED_CORES

    current = registry if registry is not None else GameEmulatorRegistry.from_environment()
    inventory = canonical_targets()
    current_rows = current.catalog()
    row_map = {r["target_id"]: r for r in current_rows}
    if set(row_map) != set(inventory):
        raise ValueError("Canonical hardware matrix and current operator registry catalog differ")
    rows = []
    for target_id in sorted(inventory):
        meta = inventory[target_id]
        catalog = row_map[target_id]
        choices = sorted(set(catalog["candidate_core_ids"]))
        recipe_cores = sorted(
            core
            for core in choices
            if core in PINNED_CORES and target_id in PINNED_CORES[core].get("targets", ())
        )
        status = catalog["readiness"]["code"]
        installed = bool(catalog["available"])
        mapped = bool(choices)
        controller = controller_layout_for_target(target_id, ["joypad"])
        core_options = []
        for option in catalog["core_installations"]:
            recipe = PINNED_CORES.get(option["core_id"]) if option["core_id"] in recipe_cores else None
            core_options.append(
                dict(
                    option,
                    source_recipe=(
                        {
                            "revision": recipe["revision"],
                            "candidate_only": bool(recipe.get("candidate_only")),
                            "required_firmware": list(recipe.get("firmware", ())),
                            "license_review": recipe.get("license_review"),
                            "feature_limits": recipe.get("feature_limits"),
                            "source_acquisition_automatic": False,
                            "compiled_in_this_audit": False,
                        }
                        if recipe is not None
                        else None
                    ),
                    operator_actions=_core_actions(option, target_id, recipe),
                )
            )
        preferred = next((option for option in core_options if option["available"]), None)
        if preferred is None:
            preferred = next((option for option in core_options if option["installation_present"]), None)
        if preferred is None:
            preferred = next((option for option in core_options if option["source_recipe"] is not None), None)
        if preferred is None and core_options:
            preferred = core_options[0]
        if installed:
            next_action = "Boot a rights-cleared test game, qualify input/audio/video/replay, then record measured fidelity and limits"
            tier = "P0_native_qualification"
        elif any(option["installation_present"] for option in core_options):
            next_action = preferred["operator_actions"][0]["message"]
            tier = "P0_repair_installed_core"
        elif recipe_cores:
            next_action = "Build a pinned source recipe, inspect its exact ABI/firmware, approve it locally, then qualify real game boot"
            tier = "P1_install_and_approve"
        elif mapped:
            next_action = "Add and independently review an exact pinned emulator build recipe or approved installation for declared compatible core"
            tier = "P1_implement_missing_install_recipe"
        elif meta["status"] == "historical_reference":
            next_action = "Develop a legally sourced historical device research or reference-simulation adapter; do not claim runnable ROM support"
            tier = "P2_historical_reference_research"
        elif meta["status"] == "licensed_sdk":
            next_action = "Obtain lawful developer SDK access or provide a separately governed native adapter; no unauthorized console emulation"
            tier = "P2_licensed_sdk_required"
        else:
            next_action = "Implement and qualify an appropriate native/toolchain adapter or locate a verifiable legal emulator core mapping"
            tier = "P2_external_adapter_needed"
        rows.append(
            {
                "target_id": target_id,
                "family": meta["family"],
                "year": meta["year"],
                "platform_availability": meta["status"],
                "declared_core_candidate_count": len(choices),
                "declared_core_ids": choices,
                "pinned_recipe_cores": recipe_cores,
                "installed_approved_core_present": installed,
                "current_operator_readiness_code": status,
                "current_operator_readiness_message": catalog["readiness"]["message"],
                "selected_core": catalog["core"],
                "core_options": core_options,
                "native_execution_available": installed,
                "source_recipe_only": not installed
                and not any(option["installation_present"] for option in core_options)
                and bool(recipe_cores),
                "operator_actions": (
                    preferred["operator_actions"]
                    if preferred is not None
                    else [
                        {
                            "code": tier.removeprefix("P2_"),
                            "message": next_action,
                            "argv": [],
                            "automatic": False,
                            "operator_only": True,
                        }
                    ]
                ),
                "hardware_style_controller_profile": controller["profile_name"],
                "generic_retropad_fallback": controller["generic_fallback"],
                "actual_native_controller_compatibility_verified": False,
                "real_rom_boot_qualified": False,
                "audio_video_accuracy_qualified": False,
                "replay_and_savestate_qualified": False,
                "heldout_ai_learning_gain_proven": False,
                "priority_tier": tier,
                "next_action": next_action,
            }
        )
    totals = Counter(row["priority_tier"] for row in rows)
    summary = {
        "canonical_target_count": len(rows),
        "declared_native_core_mapping_targets": sum(bool(row["declared_core_ids"]) for row in rows),
        "targets_without_native_core_mapping": sum(not row["declared_core_ids"] for row in rows),
        "installed_approved_core_targets": sum(row["installed_approved_core_present"] for row in rows),
        "mapped_targets_without_approved_core": sum(
            bool(row["declared_core_ids"]) and not row["installed_approved_core_present"] for row in rows
        ),
        "mapped_targets_with_pinned_install_recipe": sum(bool(row["pinned_recipe_cores"]) for row in rows),
        "generic_controller_fallback_targets": sum(row["generic_retropad_fallback"] for row in rows),
        "named_or_approximate_controller_targets": sum(not row["generic_retropad_fallback"] for row in rows),
        "real_rom_boot_qualified_in_this_audit": 0,
        "verified_physical_controller_layouts": 0,
        "priority_counts": dict(sorted(totals.items())),
        "installed_core_repairs_required": sum(
            row["priority_tier"] == "P0_repair_installed_core" for row in rows
        ),
        "source_recipe_only_targets": sum(row["source_recipe_only"] for row in rows),
    }
    result = {
        "schema_version": SCHEMA,
        "source": "canonical Dragon hardware + actual operator-approved registry + pinned open-source build recipes",
        "registry_sha256": current.registry_digest,
        "summary": summary,
        "targets": rows,
        "core_binary_execution_performed": False,
        "actual_native_game_qualification_performed": False,
        "homebrew_licensing_independently_verified": False,
        "deployment_platform_qualified": False,
        "model_weights_changed": False,
    }
    result["matrix_sha256"] = digest(result)
    return result


def render_emulator_gap_dashboard(report: dict[str, Any]) -> str:
    """Single-file offline viewer: no CDNs, raw source/game content or API calls."""
    import json

    if report.get("schema_version") != SCHEMA or not isinstance(report.get("targets"), list):
        raise ValueError("169-target dashboard requires the exact target matrix")
    safe_data = (
        json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
        .replace("&", r"\u0026")
    )
    template = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skeleton · 169-target emulator readiness</title>
<style>:root{color-scheme:dark;background:#101725;color:#e7effc;font:14px system-ui,sans-serif}
body{max-width:1440px;margin:auto;padding:18px}header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap}
h1{font-size:24px}small{color:#afc1d7}table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid #354159;padding:9px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:#1b293c}td{font-size:12px}input,select{background:#19283c;border:1px solid #647b94;color:white;padding:9px;border-radius:8px}
.filters{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}input{min-width:240px;flex:1}
.stat{display:inline-flex;flex-direction:column;background:#1a293c;border:1px solid #40526b;border-radius:9px;padding:11px;margin:4px;min-width:150px}
.stat strong{font-size:22px}.warning{color:#f1d398}.good{color:#a7d5ae}.scroll{overflow-x:auto}
code{font-size:11px;overflow-wrap:anywhere}.next{min-width:260px;max-width:420px}
</style></head><body>
<header><h1>Emulator hardware readiness matrix</h1><small>Actual installed cores, declared mappings and training qualification are separate facts</small></header>
<section id="summary"></section>
<div class="filters"><input id="search" aria-label="Search by target or family" placeholder="Search 169 targets…">
<select id="filter" aria-label="Filter readiness"><option value="all">All targets</option>
<option value="installed">Operator-approved native core</option>
<option value="mapped">Mapped, not installed/approved</option>
<option value="unmapped">No declared native core mapping</option>
<option value="generic">Generic controller fallback</option></select>
<small id="visible"></small></div>
<div class="scroll"><table><thead><tr>
<th>Hardware target</th><th>Core mapping / installed status</th>
<th>Controller</th><th>Next executable work</th>
</tr></thead><tbody id="rows"></tbody></table></div>
<p><small>This catalog does not certify 169 functional emulators, gameplay success or physical hardware accuracy.
Installed metadata is not boot evidence. Browser report has no external requests.</small></p>
<script>
const report=__DATA__;
const $=id=>document.getElementById(id);
const text=(tag,value)=>{let el=document.createElement(tag);el.textContent=String(value);return el};
const total=report.summary;
for(const [key,value] of [
 ["Canonical targets",total.canonical_target_count],
 ["Declared libretro mappings",total.declared_native_core_mapping_targets],
 ["Missing core mappings",total.targets_without_native_core_mapping],
 ["Approved installed targets",total.installed_approved_core_targets],
 ["Generic controller panels",total.generic_controller_fallback_targets],
 ["Proven native game boots",total.real_rom_boot_qualified_in_this_audit]
]){const div=text("div","");div.className="stat";div.append(text("small",key),text("strong",value));$("summary").append(div)}
function render(){
 const filter=$("filter").value,term=$("search").value.trim().toLowerCase();
 const selected=report.targets.filter(t=>{
  const kind=filter==="all"||
   (filter==="installed"&&t.installed_approved_core_present)||
   (filter==="mapped"&&t.declared_core_candidate_count>0&&!t.installed_approved_core_present)||
   (filter==="unmapped"&&t.declared_core_candidate_count===0)||
   (filter==="generic"&&t.generic_retropad_fallback);
  return kind&&(t.target_id.toLowerCase().includes(term)||t.family.toLowerCase().includes(term)||
      t.declared_core_ids.some(x=>x.includes(term)));
 });
 $("rows").replaceChildren();
 for(const t of selected){
  const tr=document.createElement("tr");
  const a=document.createElement("td");a.append(text("strong",t.target_id),text("div",t.family+" · "+t.year));
  const b=document.createElement("td");
  b.append(text("strong",t.installed_approved_core_present?"Approved installation (unqualified)":
        t.declared_core_candidate_count?"Mapped, install/approval pending":"No declared core mapping"));
  b.append(text("div",t.declared_core_ids.join(", ")||"External adapter needed"));
  b.append(text("small",t.current_operator_readiness_code+": "+t.current_operator_readiness_message));
  for(const core of t.core_options){
   const detail=document.createElement("details");
   detail.append(text("summary",core.core_id+" · "+core.readiness.code));
   const admission=core.content_admission;
   detail.append(text("div","Admitted suffix hints: "+(admission.admitted_entrypoint_extensions.join(", ")||"Actual core inspection required")));
   if(admission.unsupported_descriptor_extensions.length)
    detail.append(text("div","Unsupported descriptor closure: "+admission.unsupported_descriptor_extensions.join(", ")));
   if(core.source_recipe){detail.append(text("div","Pinned source: "+core.source_recipe.revision));
    if(core.source_recipe.required_firmware.length)detail.append(text("div","Required lawful firmware: "+core.source_recipe.required_firmware.join(", ")));
    if(core.source_recipe.feature_limits)detail.append(text("div",core.source_recipe.feature_limits));
    if(core.source_recipe.license_review)detail.append(text("div",core.source_recipe.license_review));}
   for(const action of core.operator_actions){detail.append(text("p",action.message));
    if(action.argv.length)detail.append(text("code",action.argv.join(" ")));}
   b.append(detail);
  }
  const c=document.createElement("td");c.textContent=t.hardware_style_controller_profile;
  if(t.generic_retropad_fallback)c.className="warning";
  const d=document.createElement("td");d.className="next";d.append(text("small",t.priority_tier),
   text("div",t.next_action));
  for(const action of t.operator_actions){d.append(text("p",action.message));
   if(action.argv.length)d.append(text("code",action.argv.join(" ")));}
  tr.append(a,b,c,d);$("rows").append(tr);
 }
 $("visible").textContent=selected.length+" of "+total.canonical_target_count+" shown";
}
$("filter").addEventListener("change",render);$("search").addEventListener("input",render);render();
</script></body></html>"""
    return template.replace("__DATA__", safe_data)
