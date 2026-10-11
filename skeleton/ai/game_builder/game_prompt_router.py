"""User prompt -> real capabilities and supervised exact-source edit suggestions.

Routing is deterministic offline intent analysis, *not* a claim of a live
Jeeves/Dragon model. Their generated source can enter through typed external
drafts, but the local source workspace requires review and explicit commit.
All programmatic edits are targeted file patches, never arbitrary scripts.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .contracts import canonical_digest
from .game_project_workspace import GameWorkspace,WorkspaceError,FileVersion


class PromptRoutingError(ValueError):
    """Unsupported original-game authoring prompt or source target."""


@dataclass(frozen=True,slots=True)
class AuthoringAxis:
    key: str
    hints: tuple[str,...]
    targets: tuple[str,...]
    engine: str
    priority: int
    reviewer: str
    capabilities: tuple[str,...] = ()

    def payload(self):
        return dict(key=self.key,engine=self.engine,priority=self.priority,
                    reviewer=self.reviewer,targets=list(self.targets),
                    capabilities=list(self.capabilities))


AXES=(
    AuthoringAxis("story_continuity",("story","lore","arc","ending","canon","plot","narrative","epilogue"),
                  ("game/director.json","notes/story.md"),"director",98,"wiki",
                  ("mission.endings","scene.data")),
    AuthoringAxis("quest_solver",("quest","puzzle","solution","objective","mission","reward","victory","time trial","escort"),
                  ("game/director.json","missions/solution_branches.json"),"mission",100,"mirror",
                  ("mission.algebra","mission.solver")),
    AuthoringAxis("cinematography",("cutscene","camera","cinematic","storyboard","shot","dialogue","sequence"),
                  ("game/director.json","cinematics/shot_list.json"),"scene",90,"human",
                  ("scene.cinematic",)),
    AuthoringAxis("npc_behavior",("npc","citizen","character","personality","emotion","memory","routine","needs"),
                  ("npcs/original_roster.json","npcs/behavior_notes.md"),"npc",96,"wiki",
                  ("npc.needs","npc.memory")),
    AuthoringAxis("npc_story_witness",("witness","witnessed","saw","rumor","gossip","testimony","reactive quest","reaction"),
                  ("npcs/witness_rules.json","missions/witness_outcomes.json"),"npc",100,"mirror",
                  ("npc.memory","mission.algebra")),
    AuthoringAxis("social_factions",("faction","relationship","friendship","reputation","kinship","bond","society"),
                  ("npcs/factions.json","npcs/relationship_rules.json"),"npc",90,"wiki",
                  ("npc.social",)),
    AuthoringAxis("economy",("economy","trade","craft","market","harvest","production","resource"),
                  ("npcs/economy.json","missions/profession_quests.json"),"npc",86,"mirror",
                  ("npc.social",)),
    AuthoringAxis("geometry",("level","region","layout","building","maze","scene","world","terrain"),
                  ("game/director.json","scenes/level_map.json"),"scene",90,"human",
                  ("scene.data",)),
    AuthoringAxis("combat",("combat","battle","fight","weapon","enemy","survival","waves","rival"),
                  ("missions/combat.json","npcs/combat_ai.json"),"mission",89,"mirror",
                  ("mission.solver","npc.needs")),
    AuthoringAxis("accessibility",("accessibility","caption","subtitle","colorblind","localization","contrast"),
                  ("notes/accessibility.md","cinematics/subtitles.json"),"product",84,"human",
                  ("scene.cinematic",)),
    AuthoringAxis("performance",("performance","fps","lod","memory budget","gpu","cpu","mobile","handheld"),
                  ("engine/device_profile.json","notes/performance.md"),"director",93,"mirror",
                  ("director.synergy",)),
    AuthoringAxis("legal_provenance",("rights","copyright","license","attribution","plagiarism","homebrew"),
                  ("reviews/source_rights.json","notes/originality.md"),"product",100,"human",
                  ("product.browser",)),
    AuthoringAxis("training_review",("learn","training","mirror","adversarial","distill","knowledge","almanac"),
                  ("reviews/mirror_plan.json","almanacs/learning_plan.json"),"mirror",100,"wiki",
                  ("director.mirror",)),
    AuthoringAxis("audio",("music","sound","voice","ambient","sfx","instrument"),
                  ("cinematics/audio_cues.json","notes/sound_design.md"),"scene",78,"human",
                  ("scene.cinematic",)),
    AuthoringAxis("demo",("demo","prototype","practice","playtest","shipping","release"),
                  ("notes/release_plan.md","reviews/consumer_gate.json"),"product",92,"human",
                  ("product.browser",)),
)


@dataclass(frozen=True,slots=True)
class EditTarget:
    path: str
    exists: bool
    sha256: str
    axis: str
    reason: str
    approval_required: bool = True

    def payload(self):
        return dict(path=self.path,exists=self.exists,sha256=self.sha256,
                    axis=self.axis,reason=self.reason,
                    approval_required=self.approval_required)


@dataclass(frozen=True,slots=True)
class PromptPlan:
    prompt_digest: str
    project: str
    axes: tuple[AuthoringAxis,...]
    files: tuple[EditTarget,...]
    guidance: tuple[str,...]
    tool_authority: str

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.prompt_edit_plan.v1",
                    project=self.project,prompt_digest=self.prompt_digest,
                    axes=[a.payload() for a in self.axes],
                    files=[f.payload() for f in self.files],
                    guidance=list(self.guidance),
                    tool_authority=self.tool_authority,
                    generated_source_code=False,
                    model_inference_performed=False,
                    human_supervision_required=True)


def route_game_prompt(workspace: GameWorkspace,prompt: str,*,project: str,
                      max_targets: int=16,authorized: bool)->PromptPlan:
    if not authorized:
        raise PermissionError("AI prompt planning needs local designer authority")
    if not isinstance(workspace,GameWorkspace):
        raise PromptRoutingError("initialized game workspace required")
    if project!=workspace.active():
        raise PromptRoutingError("never route AI changes toward inactive game projects")
    if not isinstance(prompt,str) or not 12<=len(prompt)<=20000:
        raise PromptRoutingError("original user request must be concrete and bounded")
    if type(max_targets) is not int or not 1<=max_targets<=32:
        raise PromptRoutingError("bounded targeted source plan required")
    lowered=prompt.casefold()
    selected=sorted(
        (axis for axis in AXES if any(
            re.search(r"(?<![a-z0-9])"+re.escape(hint)+r"(?![a-z0-9])",
                      lowered) for hint in axis.hints
        )),key=lambda x:(-x.priority,x.key),
    )
    if not selected:
        selected=[next(a for a in AXES if a.key=="geometry"),
                  next(a for a in AXES if a.key=="story_continuity")]
    found={f.path:f for f in workspace.files("current",project)}
    targets={}
    for axis in selected:
        for location in axis.targets:
            if location in targets:
                continue
            version=found.get(location)
            targets[location]=EditTarget(
                location,version is not None,
                version.sha256 if version else
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                axis.key,"Targeted "+axis.engine+" change requested by original user",
            )
            if len(targets)>=max_targets:
                break
        if len(targets)>=max_targets:break
    return PromptPlan(
        canonical_digest({"project":project,"prompt":prompt}),project,
        tuple(selected),tuple(targets.values()),(
            "Present affected file paths and their exact SHA-256 source bases.",
            "Generate isolated candidate content with Jeeves/Dragon externally; "
            "the offline router does not impersonate a language model.",
            "Propose one atomic file edit and run real proof/mirror gates.",
            "Require a visible human diff review and explicit commit.",
            "Archive prior project version before major authored-world changes.",
            "Never modify demo/previous trees or public-release status without approvals.",
        ),"propose_only_until_explicit_human_commit",
    )


def ingest_ai_draft(workspace: GameWorkspace,plan: PromptPlan,draft: dict,*,
                    authorized: bool)->dict:
    if not authorized:
        raise PermissionError("AI submitted edits require operator authority")
    if not isinstance(plan,PromptPlan) or not isinstance(draft,dict):
        raise PromptRoutingError("bound original prompt plan and typed AI draft required")
    if set(draft)!={"source","target","replacement","base_sha256","explanation"}:
        raise PromptRoutingError("AI draft may contain exactly one targeted file replacement")
    if draft["source"] not in {"jeeves","dragon","human"}:
        raise PromptRoutingError("unknown or unaudited game-building AI source")
    by_path={x.path:x for x in plan.files}
    target=by_path.get(draft["target"])
    if (plan.project!=workspace.active() or target is None
            or draft["base_sha256"]!=target.sha256):
        raise PromptRoutingError("AI draft changed target or stale source approval")
    if not isinstance(draft["explanation"],str) or len(draft["explanation"])<15:
        raise PromptRoutingError("AI must explain the technical purpose of its changes")
    result=workspace.propose(
        plan.project,target.path,draft["replacement"],
        expected_sha256=target.sha256,
        reason="Source "+draft["source"]+": "+draft["explanation"],
        authorized=True,
    )
    return dict(**result,agent_source=draft["source"],
                plan_digest=plan.digest,
                model_weights_changed=False,
                automatically_committed=False)


__all__=[
    "PromptRoutingError","AuthoringAxis","AXES","EditTarget","PromptPlan",
    "route_game_prompt","ingest_ai_draft",
]
