"""Structured game-creation planning for GameForge.

Turns sparse questionnaire input into an engine-neutral, validated design
contract before Forge materialisation. The planner is deterministic so the
same intake yields the same systems, scope budget, loop and play-test probes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class GameSystem:
    name: str
    purpose: str
    depends_on: Tuple[str, ...] = ()
    acceptance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["depends_on"] = list(self.depends_on)
        return data


@dataclass(frozen=True)
class PlaytestProbe:
    name: str
    scenario: str
    success_signal: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CreationAssessment:
    ok: bool
    errors: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()
    checks: Mapping[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks": dict(self.checks),
        }


@dataclass(frozen=True)
class GameCreationPlan:
    title: str
    genre: str
    era: str
    perspective: str
    audience: str
    scope: str
    fantasy: str
    pillars: Tuple[str, ...]
    player_verbs: Tuple[str, ...]
    core_loop: Tuple[str, ...]
    systems: Tuple[GameSystem, ...]
    content_budget: Mapping[str, int]
    milestones: Tuple[str, ...]
    playtests: Tuple[PlaytestProbe, ...]
    assumptions: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "genre": self.genre,
            "era": self.era,
            "perspective": self.perspective,
            "audience": self.audience,
            "scope": self.scope,
            "fantasy": self.fantasy,
            "pillars": list(self.pillars),
            "player_verbs": list(self.player_verbs),
            "core_loop": list(self.core_loop),
            "systems": [system.to_dict() for system in self.systems],
            "content_budget": dict(self.content_budget),
            "milestones": list(self.milestones),
            "playtests": [probe.to_dict() for probe in self.playtests],
            "assumptions": list(self.assumptions),
        }

    def to_build_plan(self) -> Dict[str, Any]:
        combat_genres = {"action", "rpg", "shooter", "survival", "roguelike"}
        return {
            "spawn_weapon": self.genre in combat_genres,
            "extract_late": self.era == "extraction_now",
            "briefing": self.fantasy,
            "game_creation": self.to_dict(),
        }


@dataclass(frozen=True)
class GameCreationResult:
    plan: GameCreationPlan
    assessment: CreationAssessment
    repair_rounds: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "assessment": self.assessment.to_dict(),
            "repair_rounds": self.repair_rounds,
        }


class GameCreationPlanner:
    """Compile vague game intent into a validated, bounded creation plan."""

    _ERA_GENRE = {
        "soulslike": "action",
        "boomer_shooter": "shooter",
        "arcade_golden_age": "action",
        "cozy_wholesome": "simulation",
        "horror_survival": "survival",
        "extraction_now": "shooter",
        "modern_aaa": "action",
        "indie_experimental": "adventure",
    }
    _GENRE_ALIASES = {
        "fps": "shooter", "tps": "shooter", "role-playing": "rpg",
        "roleplaying": "rpg", "rogue-like": "roguelike",
        "rogue-lite": "roguelike", "roguelite": "roguelike",
        "platform": "platformer", "sim": "simulation",
    }
    _KNOWN_GENRES = {
        "action", "adventure", "rpg", "shooter", "survival", "roguelike",
        "strategy", "puzzle", "platformer", "simulation",
    }
    _SCOPE_BUDGETS = {
        "prototype": {"locations": 1, "encounter_archetypes": 2, "npcs": 2, "objectives": 2, "mechanics": 4},
        "small": {"locations": 3, "encounter_archetypes": 5, "npcs": 6, "objectives": 8, "mechanics": 6},
        "medium": {"locations": 8, "encounter_archetypes": 10, "npcs": 16, "objectives": 20, "mechanics": 10},
        "large": {"locations": 16, "encounter_archetypes": 18, "npcs": 32, "objectives": 40, "mechanics": 14},
    }

    def create(self, *, intake: Any, answers: Mapping[str, Any], title: str,
               max_repair_rounds: int = 2) -> GameCreationResult:
        plan = self._draft(intake=intake, answers=answers, title=title)
        assessment = self.assess(plan)
        rounds = 0
        while not assessment.ok and rounds < max_repair_rounds:
            plan = self.repair(plan)
            assessment = self.assess(plan)
            rounds += 1
        return GameCreationResult(plan=plan, assessment=assessment, repair_rounds=rounds)

    def _draft(self, *, intake: Any, answers: Mapping[str, Any], title: str) -> GameCreationPlan:
        era = str(getattr(intake, "era", "extraction_now") or "extraction_now")
        genre = self.infer_genre(answers, era)
        perspective = self._text(answers.get("perspective"), "third-person")
        audience = self._text(answers.get("audience"), "general")
        scope = self._scope(answers.get("scope"))
        fantasy = self._fantasy(answers, genre=genre, era=era, title=title)
        loop = self._core_loop(genre)
        return GameCreationPlan(
            title=title,
            genre=genre,
            era=era,
            perspective=perspective,
            audience=audience,
            scope=scope,
            fantasy=fantasy,
            pillars=self._pillars(genre, era, answers),
            player_verbs=self._verbs(genre),
            core_loop=loop,
            systems=self._systems(genre, era),
            content_budget=dict(self._SCOPE_BUDGETS[scope]),
            milestones=(
                "graybox the complete player loop",
                "prove one vertical-slice encounter",
                "integrate progression and failure recovery",
                "fill content only after the loop is stable",
                "balance, accessibility, performance and release verification",
            ),
            playtests=self._playtests(genre, loop),
            assumptions=self._assumptions(answers, genre, scope),
        )

    def infer_genre(self, answers: Mapping[str, Any], era: str) -> str:
        raw = self._text(answers.get("genre"), "").lower().replace("_", "-")
        raw = self._GENRE_ALIASES.get(raw, raw)
        if raw in self._KNOWN_GENRES:
            return raw
        haystack = " ".join(
            self._text(answers.get(key), "").lower()
            for key in ("concept", "theme", "description", "fantasy", "vision")
        )
        keywords = (
            ("roguelike", ("roguelike", "roguelite", "procedural run")),
            ("rpg", ("rpg", "role playing", "role-playing")),
            ("shooter", ("shooter", "fps", "gun", "firearm")),
            ("survival", ("survival", "horror", "scarcity")),
            ("strategy", ("strategy", "tactics", "rts", "4x")),
            ("puzzle", ("puzzle", "logic game")),
            ("platformer", ("platformer", "platforming")),
            ("simulation", ("simulation", "simulator", "cozy")),
            ("adventure", ("adventure", "exploration", "narrative")),
        )
        for genre, words in keywords:
            if any(word in haystack for word in words):
                return genre
        return self._ERA_GENRE.get(era, "action")

    def assess(self, plan: GameCreationPlan) -> CreationAssessment:
        errors = []
        warnings = []
        names = [system.name for system in plan.systems]
        name_set = set(names)
        unique_systems = len(names) == len(name_set)
        if not unique_systems:
            errors.append("system names must be unique")
        dangling = sorted({dep for system in plan.systems for dep in system.depends_on if dep not in name_set})
        dependencies_resolve = not dangling
        if dangling:
            errors.append("unknown system dependencies: " + ", ".join(dangling))
        acyclic = not self._has_dependency_cycle(plan.systems)
        if not acyclic:
            errors.append("system dependency graph contains a cycle")
        loop_complete = len(plan.core_loop) >= 4 and len(set(plan.core_loop)) >= 4
        if not loop_complete:
            errors.append("core loop needs at least four distinct stages")
        verbs_present = len(plan.player_verbs) >= 3
        if not verbs_present:
            errors.append("at least three player verbs are required")
        budget_bounded = all(isinstance(value, int) and value >= 0 for value in plan.content_budget.values())
        if not budget_bounded:
            errors.append("content budget values must be non-negative integers")
        playtest_coverage = len(plan.playtests) >= 4 and all(p.success_signal.strip() for p in plan.playtests)
        if not playtest_coverage:
            errors.append("playtest plan lacks measurable coverage")
        if plan.scope == "large":
            warnings.append("large scope should be unlocked only after vertical-slice evidence")
        if plan.content_budget.get("mechanics", 0) > 12:
            warnings.append("mechanic count is high; prefer depth before breadth")
        return CreationAssessment(
            ok=not errors,
            errors=tuple(errors),
            warnings=tuple(warnings),
            checks={
                "unique_systems": unique_systems,
                "dependencies_resolve": dependencies_resolve,
                "acyclic_dependencies": acyclic,
                "core_loop_complete": loop_complete,
                "player_verbs_present": verbs_present,
                "content_budget_bounded": budget_bounded,
                "playtest_coverage": playtest_coverage,
            },
        )

    def repair(self, plan: GameCreationPlan) -> GameCreationPlan:
        systems = self._dedupe_systems(plan.systems)
        names = {system.name for system in systems}
        systems = tuple(
            GameSystem(system.name, system.purpose,
                       tuple(dep for dep in system.depends_on if dep in names and dep != system.name),
                       system.acceptance)
            for system in systems
        )
        if self._has_dependency_cycle(systems):
            systems = tuple(
                GameSystem(system.name, system.purpose,
                           (() if index == 0 else (systems[index - 1].name,)),
                           system.acceptance)
                for index, system in enumerate(systems)
            )
        verbs = plan.player_verbs
        if len(verbs) < 3:
            verbs = tuple(dict.fromkeys((*verbs, "observe", "choose", "act")))
        loop = plan.core_loop
        if len(set(loop)) < 4:
            loop = ("read the state", "choose an approach", "act", "read feedback", "progress")
        playtests = plan.playtests if len(plan.playtests) >= 4 else self._playtests(plan.genre, loop)
        return GameCreationPlan(
            title=plan.title, genre=plan.genre, era=plan.era,
            perspective=plan.perspective, audience=plan.audience, scope=plan.scope,
            fantasy=plan.fantasy, pillars=plan.pillars, player_verbs=tuple(verbs),
            core_loop=tuple(loop), systems=systems,
            content_budget={key: max(0, int(value)) for key, value in plan.content_budget.items()},
            milestones=plan.milestones, playtests=tuple(playtests),
            assumptions=tuple((*plan.assumptions, "structural planner repair applied")),
        )

    def _systems(self, genre: str, era: str) -> Tuple[GameSystem, ...]:
        systems = [
            GameSystem("player_control", "translate intent into readable movement and actions", (), "input produces immediate, reversible feedback"),
            GameSystem("game_rules", "resolve legal actions and authoritative world rules", ("player_control",), "same state and input resolve deterministically"),
        ]
        combat = genre in {"action", "rpg", "shooter", "survival", "roguelike"}
        if combat:
            systems.extend((
                GameSystem("encounter_director", "pace threats and encounter pressure", ("game_rules",), "encounters have readable start, escalation and end states"),
                GameSystem("encounter_resolution", "resolve damage, resources and encounter outcomes", ("encounter_director",), "success and failure both produce recoverable state"),
            ))
            feedback_dep = "encounter_resolution"
        else:
            systems.append(GameSystem("interaction_model", "resolve world interactions and authored affordances", ("game_rules",), "interactions expose consequence before irreversible commitment"))
            feedback_dep = "interaction_model"
        systems.extend((
            GameSystem("feedback", "surface state changes through audiovisual and UI feedback", (feedback_dep,), "players can explain why the last outcome happened"),
            GameSystem("progression", "convert mastery and rewards into meaningful future options", ("feedback",), "rewards change future decisions instead of only raising numbers"),
            GameSystem("objective_director", "sequence goals, completion and failure recovery", ("progression",), "a new player can identify the next meaningful goal"),
            GameSystem("telemetry", "capture loop health, failures and progression signals", ("objective_director",), "playtest probes can be measured from emitted events"),
        ))
        if era == "extraction_now":
            systems.append(GameSystem("risk_extraction", "make carried value compete with continued risk", ("objective_director",), "players face a meaningful stay-or-leave decision"))
        return tuple(systems)

    def _core_loop(self, genre: str) -> Tuple[str, ...]:
        loops = {
            "shooter": ("read threat and cover", "choose position and tool", "engage", "collect tactical feedback and resources", "reposition or push the objective"),
            "survival": ("survey risk and scarcity", "choose a route", "spend or preserve resources", "survive the consequence", "secure progress and adapt"),
            "rpg": ("discover an objective", "choose an approach", "resolve dialogue or conflict", "receive consequence and reward", "develop the build and world state"),
            "roguelike": ("read the generated challenge", "choose a build decision", "commit to the encounter", "convert risk into rewards", "adapt the run and advance"),
            "strategy": ("gather intelligence and resources", "form a plan", "commit units or actions", "resolve the simulation", "adapt and expand"),
            "puzzle": ("inspect the state", "form a hypothesis", "make a move", "read feedback", "internalize the rule and unlock complexity"),
            "platformer": ("read the route", "move and time traversal", "clear a hazard", "recover or collect", "attempt a harder route"),
            "simulation": ("observe the system", "choose an intervention", "run the simulation", "read consequences", "refine and grow"),
            "adventure": ("discover a lead", "explore", "interact or choose", "receive narrative or world feedback", "unlock the next lead"),
            "action": ("read the challenge", "choose an approach", "act", "read consequence and reward", "master a harder challenge"),
        }
        return loops.get(genre, loops["action"])

    def _verbs(self, genre: str) -> Tuple[str, ...]:
        return {
            "shooter": ("move", "aim", "fire", "evade", "loot"),
            "survival": ("scout", "move", "use", "craft", "escape"),
            "rpg": ("explore", "talk", "fight", "choose", "develop"),
            "roguelike": ("explore", "fight", "build", "risk", "adapt"),
            "strategy": ("inspect", "plan", "deploy", "command", "adapt"),
            "puzzle": ("inspect", "manipulate", "test", "undo", "solve"),
            "platformer": ("run", "jump", "climb", "evade", "collect"),
            "simulation": ("inspect", "place", "tune", "run", "optimize"),
            "adventure": ("explore", "inspect", "talk", "use", "choose"),
            "action": ("move", "target", "act", "evade", "interact"),
        }.get(genre, ("observe", "move", "act", "interact", "choose"))

    def _pillars(self, genre: str, era: str, answers: Mapping[str, Any]) -> Tuple[str, ...]:
        pillars = ["readable cause and effect", "meaningful player decisions", "fast recovery from failure"]
        if genre in {"rpg", "adventure"}:
            pillars[2] = "consequences that persist in world state"
        elif genre in {"survival", "roguelike"}:
            pillars[2] = "risk that changes future choices"
        elif genre == "simulation":
            pillars[2] = "systems that create understandable emergence"
        if era == "cozy_wholesome":
            pillars[2] = "low-friction recovery and expressive progress"
        custom = self._text(answers.get("pillar"), "")
        if custom:
            pillars.append(custom)
        return tuple(dict.fromkeys(pillars))

    def _playtests(self, genre: str, core_loop: Sequence[str]) -> Tuple[PlaytestProbe, ...]:
        return (
            PlaytestProbe("first-minute clarity", "start with no instructions beyond diegetic or UI cues", "tester performs a primary verb without outside explanation"),
            PlaytestProbe("loop completion", f"play through: {' -> '.join(core_loop)}", "tester completes one full loop and can describe its stages"),
            PlaytestProbe("failure recovery", "force a common failure during the primary challenge", "tester understands the cause and re-enters play quickly"),
            PlaytestProbe("decision value", "present two viable approaches to the same objective", "tester can explain a meaningful trade-off between choices"),
            PlaytestProbe("progression value", "grant the first progression reward", "reward changes a subsequent decision or capability"),
            PlaytestProbe("content pressure", f"repeat the core {genre} loop with varied content", "variation changes tactics without introducing a new core rule"),
        )

    def _fantasy(self, answers: Mapping[str, Any], *, genre: str, era: str, title: str) -> str:
        for key in ("fantasy", "concept", "description", "theme"):
            value = self._text(answers.get(key), "")
            if value:
                return value
        return f"Master a {genre} world in the {era.replace('_', ' ')} design dialect of {title}."

    def _assumptions(self, answers: Mapping[str, Any], genre: str, scope: str) -> Tuple[str, ...]:
        assumptions = []
        if not self._text(answers.get("genre"), ""):
            assumptions.append(f"genre inferred as {genre} from intake/era")
        if not self._text(answers.get("scope"), ""):
            assumptions.append(f"scope defaulted to {scope}")
        if not self._text(answers.get("perspective"), ""):
            assumptions.append("perspective defaulted to third-person")
        return tuple(assumptions)

    def _scope(self, value: Any) -> str:
        raw = self._text(value, "small").lower().replace("_", "-")
        raw = {"vertical-slice": "prototype", "vertical slice": "prototype", "indie": "small", "aaa": "large"}.get(raw, raw)
        return raw if raw in self._SCOPE_BUDGETS else "small"

    @staticmethod
    def _text(value: Any, default: str) -> str:
        text = "" if value is None else str(value).strip()
        return text or default

    @staticmethod
    def _dedupe_systems(systems: Iterable[GameSystem]) -> Tuple[GameSystem, ...]:
        result = []
        seen = set()
        for system in systems:
            if system.name not in seen:
                result.append(system)
                seen.add(system.name)
        return tuple(result)

    @staticmethod
    def _has_dependency_cycle(systems: Sequence[GameSystem]) -> bool:
        graph = {system.name: tuple(system.depends_on) for system in systems}
        visiting, visited = set(), set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for dependency in graph.get(node, ()):
                if dependency in graph and visit(dependency):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in graph if node not in visited)
