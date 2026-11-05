"""Command-line playable Lantern Quay campaign, checkpoint and replay verifier."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, canonical, decode, demo_actions,
    export_bundle, load_source, verify_bundle,
)
from .harbor_crafting_authoring import author_revision, verify_revision
from .harbor_crafting_planner import solve, verify_plan
from .harbor_crafting_missions import mission_report, verify_mission_report, solve_missions
from .harbor_crafting_mission_authoring import author_mission_revision, verify_mission_revision
from .harbor_crafting_mission_branches import mission_branch_report, verify_mission_branch_report
from .harbor_crafting_mission_compare import compare_mission_revision, verify_mission_comparison
from .harbor_crafting_package import MAX_PACKAGE_BYTES, build_package, verify_package, play_package, verify_package_play
from .harbor_crafting_market import market_report, verify_market_report, market_checkpoint, market_resume, market_futures, verify_market_futures
from .harbor_crafting_market_preview import preview_market, verify_market_preview, apply_market_preview, MAX_BYTES as MAX_PREVIEW_BYTES
from .harbor_crafting_market import MAX_BYTES as MAX_MARKET_BYTES
from .harbor_crafting_market_balance import balance_market, verify_market_balance, MAX_BYTES as MAX_BALANCE_BYTES
from .harbor_crafting_market_distribution import build_market_distribution, verify_market_distribution, play_market_distribution, verify_market_distribution_play, MAX_BYTES as MAX_DISTRIBUTION_BYTES
from .harbor_crafting_npc import npc_observations, verify_npc_observations, npc_forecast, verify_npc_forecast, MAX_BYTES as MAX_NPC_BYTES
from .harbor_crafting_journal_merge import (
    MAX_COMPARISON_BYTES, compare_journals, fast_forward_journal,
    verify_journal_comparison,
)
from .harbor_crafting_journal import (
    MAX_JOURNAL_BYTES, append_journal, create_journal, journal_at, journal_audit,
    journal_head, rewind_journal, verify_journal,
)
from .harbor_crafting_journal_transfer import (
    MAX_TRANSFER_BYTES, export_journal_package_play, verify_journal_package_play,
)
from .harbor_crafting_guidance import (
    MAX_REPORT_BYTES as MAX_GUIDANCE_BYTES,
    legal_action_report, verify_legal_action_report,
)
from .harbor_crafting_route import MAX_ROUTE_BYTES, plan_route, verify_route
from .harbor_crafting_itinerary import (
    MAX_ITINERARY_BYTES, build_itinerary, verify_itinerary,
)
from .harbor_crafting_time_trials import (
    MAX_REPORT_BYTES as MAX_TRIAL_REPORT_BYTES,
    MAX_BOARD_BYTES as MAX_TRIAL_BOARD_BYTES,
    resume_time_trial, time_trial_report, verify_time_trial_report,
    time_trial_leaderboard, verify_time_trial_leaderboard,
)
from .harbor_crafting_time_trial_authoring import (
    MAX_REVISION_BYTES as MAX_TRIAL_REVISION_BYTES,
    author_time_trial_revision, verify_time_trial_revision,
)
from .harbor_crafting_season_authoring import (
    MAX_REVISION_BYTES as MAX_SEASON_REVISION_BYTES,
    author_season_revision, verify_season_revision,
)
from .harbor_crafting_season import (
    MAX_RECORD_BYTES as MAX_SEASON_RECORD_BYTES,
    MAX_BOARD_BYTES as MAX_SEASON_BOARD_BYTES,
    MAX_SEASON_BYTES, append_season, build_season, verify_season_record,
    season_board, verify_season_board, next_season_round,
)
from .harbor_crafting_ghost_race import (
    MAX_RACE_BYTES as MAX_GHOST_RACE_BYTES, ghost_race, verify_ghost_race,
)
from .harbor_crafting_contracts import (
    MAX_BOARD_BYTES as MAX_CONTRACT_BOARD_BYTES,
    MAX_SAVE_BYTES as MAX_CONTRACT_SAVE_BYTES,
    MAX_EDITS_BYTES as MAX_CONTRACT_EDITS_BYTES,
    build_save, append_save, play_save, next_order, verify_save, edit_board, verify_edit,
)
from .harbor_crafting_contract_solver import (
    MAX_PLAN_BYTES as MAX_CONTRACT_PLAN_BYTES,
    solve_contract, verify_contract_plan,
)
from .harbor_crafting_survey import (
    MAX_BOARD_BYTES as MAX_SURVEY_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_SURVEY_REPORT_BYTES,
    build_survey, resume_survey, verify_survey,
)
from .harbor_crafting_survey_guidance import (
    MAX_GUIDANCE_BYTES as MAX_SURVEY_HINT_BYTES,
    survey_hint, verify_survey_hint,
)
from .harbor_crafting_survey_authoring import (
    MAX_REVISION_BYTES as MAX_SURVEY_REVISION_BYTES,
    edit_survey, verify_survey_edit,
)
from .harbor_crafting_weather import (
    MAX_BOARD_BYTES as MAX_WEATHER_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_WEATHER_REPORT_BYTES,
    MAX_FORECAST_BYTES as MAX_WEATHER_FORECAST_BYTES,
    build_weather_game, resume_weather_game, verify_weather_game,
    weather_forecast, verify_weather_forecast,
)
from .harbor_crafting_weather_authoring import (
    MAX_REVISION_BYTES as MAX_WEATHER_REVISION_BYTES,
    edit_weather, verify_weather_edit,
)
from .harbor_crafting_dialogue import (
    MAX_BOARD_BYTES as MAX_DIALOGUE_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_DIALOGUE_REPORT_BYTES,
    build_dialogue_game, resume_dialogue_game, verify_dialogue_game,
)
from .harbor_crafting_dialogue_authoring import (
    MAX_REVISION_BYTES as MAX_DIALOGUE_REVISION_BYTES,
    edit_dialogue, verify_dialogue_edit,
)
from .harbor_crafting_expedition import (
    MAX_REPORT_BYTES as MAX_EXPEDITION_REPORT_BYTES,
    MAX_PACKAGE_BYTES as MAX_EXPEDITION_PACKAGE_BYTES,
    MAX_PLAY_BYTES as MAX_EXPEDITION_PLAY_BYTES,
    build_expedition, verify_expedition, resume_expedition, expedition_status,
    build_expedition_package, verify_expedition_package,
    play_expedition_package, verify_expedition_package_play,
)
from .harbor_crafting_expedition_ui import play_expedition_live
from .harbor_crafting_expedition_journal import (
    MAX_JOURNAL_BYTES as MAX_EXPEDITION_JOURNAL_BYTES,
    MAX_COMPARE_BYTES as MAX_EXPEDITION_COMPARE_BYTES,
    create_expedition_journal, verify_expedition_journal,
    append_expedition_journal, expedition_journal_at, fork_expedition_journal,
    compare_expedition_journals, verify_expedition_comparison,
    fast_forward_expedition_journal,
)
from .harbor_crafting_quest_events import (
    MAX_BOARD_BYTES as MAX_QUEST_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_QUEST_REPORT_BYTES,
    build_quest_report, verify_quest_report, quest_status,
)
from .harbor_crafting_quest_authoring import (
    MAX_REVISION_BYTES as MAX_QUEST_REVISION_BYTES,
    edit_quest_board, verify_quest_edit,
)
from .harbor_crafting_convoy import (
    MAX_BOARD_BYTES as MAX_CONVOY_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_CONVOY_REPORT_BYTES,
    build_convoy, verify_convoy, resume_convoy, convoy_status,
)
from .harbor_crafting_convoy_authoring import (
    MAX_REVISION_BYTES as MAX_CONVOY_REVISION_BYTES,
    edit_convoy_board, verify_convoy_revision,
)
from .harbor_crafting_convoy_package import (
    MAX_PACKAGE_BYTES as MAX_CONVOY_PACKAGE_BYTES,
    MAX_PLAY_BYTES as MAX_CONVOY_PLAY_BYTES,
    build_convoy_package, verify_convoy_package, play_convoy_package,
    verify_convoy_package_play, resume_convoy_package,
)
from .harbor_crafting_convoy_journal import (
    MAX_JOURNAL_BYTES as MAX_CONVOY_JOURNAL_BYTES,
    create_convoy_journal, verify_convoy_journal,
    append_convoy_journal, convoy_journal_at,
)
from .harbor_crafting_convoy_acceptance import (
    MAX_ACCEPT_BYTES as MAX_CONVOY_ACCEPT_BYTES,
    accept_convoy, verify_convoy_acceptance,
)
from .harbor_crafting_convoy_contracts import (
    MAX_BOARD_BYTES as MAX_CONVOY_CONTRACT_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_CONVOY_CONTRACT_REPORT_BYTES,
    build_convoy_contract_report, verify_convoy_contract_report,
    convoy_contract_status,
)
from .harbor_crafting_convoy_contract_authoring import (
    MAX_REVISION_BYTES as MAX_CONVOY_CONTRACT_REVISION_BYTES,
    edit_convoy_contracts, verify_convoy_contract_revision,
)
from .harbor_crafting_convoy_solver import (
    MAX_PLAN_BYTES as MAX_CONVOY_PLAN_BYTES, solve_convoy, verify_convoy_plan,
)
from .harbor_crafting_convoy_league import (
    MAX_LEAGUE_BYTES, MAX_SAVE_BYTES as MAX_LEAGUE_SAVE_BYTES,
    build_league, verify_league, resume_league, league_status,
)
from .harbor_crafting_convoy_league_package import (
    MAX_PACKAGE_BYTES as MAX_LEAGUE_PACKAGE_BYTES,
    MAX_PLAY_BYTES as MAX_LEAGUE_PLAY_BYTES,
    build_league_package, verify_league_package,
    play_league_package, verify_league_package_play, resume_league_package,
)
from .harbor_crafting_convoy_league_authoring import (
    MAX_REVISION_BYTES as MAX_LEAGUE_REVISION_BYTES,
    edit_league, verify_league_revision,
)
from .harbor_crafting_convoy_league_solver import (
    MAX_PLAN_BYTES as MAX_LEAGUE_PLAN_BYTES, solve_league, verify_league_plan,
)
from .harbor_crafting_convoy_league_journal import (
    MAX_JOURNAL_BYTES as MAX_LEAGUE_JOURNAL_BYTES,
    create_league_journal, verify_league_journal, append_league_journal,
    league_journal_at, compare_league_journals, fast_forward_league_journal,
)
from .harbor_crafting_convoy_league_board import (
    MAX_BOARD_BYTES as MAX_LEAGUE_BOARD_BYTES,
    build_league_leaderboard, verify_league_leaderboard,
)
from .harbor_crafting_convoy_league_acceptance import (
    MAX_ACCEPT_BYTES as MAX_LEAGUE_ACCEPT_BYTES,
    accept_league, verify_league_acceptance,
)
from .harbor_crafting_convoy_league_consequences import (
    MAX_CONSEQUENCE_BYTES as MAX_LEAGUE_CONSEQUENCE_BYTES,
    build_league_consequences, verify_league_consequences, compare_league_choices,
)
from .harbor_crafting_convoy_league_consequence_package import (
    MAX_PACKAGE as MAX_LEAGUE_CHOICE_PACKAGE_BYTES,
    MAX_PLAY as MAX_LEAGUE_CHOICE_PLAY_BYTES,
    build_choice_package, verify_choice_package, play_choice_package,
    verify_choice_package_play,
)
from .harbor_crafting_convoy_league_guidance import (
    MAX_GUIDANCE_BYTES as MAX_LEAGUE_GUIDANCE_BYTES,
    build_league_guidance, verify_league_guidance,
)
from .harbor_crafting_convoy_league_quests import (
    MAX_BOARD_BYTES as MAX_LEAGUE_QUEST_BOARD_BYTES,
    MAX_REPORT_BYTES as MAX_LEAGUE_QUEST_REPORT_BYTES,
    build_league_quest_report, verify_league_quest_report, league_quest_status,
)
from .harbor_crafting_convoy_league_quest_authoring import (
    MAX_REVISION_BYTES as MAX_LEAGUE_QUEST_REVISION_BYTES,
    edit_league_quests, verify_league_quest_revision,
)
from .harbor_crafting_convoy_league_ui import play_league_live
from .harbor_crafting_convoy_ui import play_convoy_live
from .harbor_crafting_ui import play_live
from .harbor_crafting_sessions import (
    branch_portfolio, checkpoint, resume_bundle, verify_portfolio,
)

DEFAULT_WORLD = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay.json"
DEFAULT_MISSIONS = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay_missions.json"
DEFAULT_CONVOY = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay_convoy.json"


def _read(path: str, maximum: int = MAX_BUNDLE_BYTES) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read(maximum + 1)
        with Path(path).open("rb") as stream:
            return stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested input") from exc


def _required_json(path: str | None, name: str, maximum: int = MAX_BUNDLE_BYTES):
    if not path:
        raise HarborError("--" + name + " is required")
    return decode(_read(path, maximum), maximum)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play, export, branch and replay-verify Lantern Quay")
    parser.add_argument("command", choices=(
        "demo", "play", "verify", "checkpoint", "resume", "portfolio", "verify-portfolio", "author", "verify-author", "solve", "verify-plan", "play-live", "mission-report", "verify-mission-report", "solve-missions", "author-missions", "verify-mission-author", "mission-checkpoint", "mission-resume", "mission-portfolio", "verify-mission-portfolio", "compare-mission-revision", "verify-mission-comparison", "package-build", "package-verify", "package-play", "package-verify-play", "market-report", "verify-market", "market-checkpoint", "market-resume", "market-futures", "verify-market-futures", "market-preview", "verify-market-preview", "market-apply", "market-balance", "verify-market-balance", "market-distribution", "verify-market-distribution", "market-distribution-play", "verify-market-distribution-play", "npc-report", "verify-npc-report", "npc-forecast", "verify-npc-forecast", "journal-init", "journal-append", "journal-verify", "journal-export", "journal-at", "journal-rewind", "journal-audit", "journal-compare", "journal-verify-comparison", "journal-fast-forward", "legal-actions", "verify-legal-actions", "journal-package-play", "journal-verify-package-play", "route-plan", "route-verify", "itinerary-build", "itinerary-verify", "trial-run", "trial-verify", "trial-resume", "trial-leaderboard", "trial-verify-leaderboard", "trial-author", "trial-verify-author", "trial-live", "ghost-race", "ghost-verify", "season-init", "season-append", "season-verify", "season-board", "season-board-verify", "season-author", "season-verify-author", "season-next", "season-live", "contract-init", "contract-next", "contract-play", "contract-append", "contract-verify", "contract-author", "contract-verify-author", "contract-live", "contract-plan", "contract-verify-plan", "survey-run", "survey-verify", "survey-resume", "survey-hint", "survey-verify-hint", "survey-author", "survey-verify-author", "weather-run", "weather-verify", "weather-resume", "weather-forecast", "weather-verify-forecast", "weather-author", "weather-verify-author", "dialogue-run", "dialogue-verify", "dialogue-resume", "dialogue-author", "dialogue-verify-author", "expedition-run", "expedition-verify", "expedition-resume", "expedition-status", "expedition-build", "expedition-verify-package", "expedition-play", "expedition-verify-play", "expedition-live", "expedition-journal-init", "expedition-journal-verify", "expedition-journal-append", "expedition-journal-at", "expedition-journal-fork", "expedition-journal-compare", "expedition-journal-verify-comparison", "expedition-journal-fast-forward", "quest-run", "quest-verify", "quest-status", "quest-author", "quest-verify-author", "convoy-run", "convoy-verify", "convoy-resume", "convoy-status", "convoy-author", "convoy-verify-author", "convoy-live", "convoy-package-build", "convoy-package-verify", "convoy-package-play", "convoy-package-verify-play", "convoy-package-resume", "convoy-journal-init", "convoy-journal-verify", "convoy-journal-append", "convoy-journal-at", "convoy-solve", "convoy-verify-plan", "convoy-contract-run", "convoy-contract-verify", "convoy-contract-status", "convoy-contract-author", "convoy-contract-verify-author", "convoy-accept", "convoy-verify-accept", "league-init", "league-run", "league-verify", "league-status", "league-resume", "league-live", "league-package-build", "league-package-verify", "league-package-play", "league-package-verify-play", "league-package-resume", "league-author", "league-verify-author", "league-solve", "league-verify-plan", "league-journal-init", "league-journal-append", "league-journal-verify", "league-journal-at", "league-journal-compare", "league-journal-fast-forward", "league-board", "league-board-verify", "league-accept", "league-verify-accept", "league-consequences", "league-verify-consequences", "league-choice-compare", "league-choice-package", "league-choice-verify-package", "league-choice-play", "league-choice-verify-play", "league-hint", "league-verify-hint", "league-quests", "league-verify-quests", "league-quest-status", "league-quest-author", "league-verify-quest-author"
    ))
    parser.add_argument("--source", default=str(DEFAULT_WORLD))
    parser.add_argument("--actions", help="JSON array file or '-' for stdin")
    parser.add_argument("--bundle", help="JSON bundle file or '-' for stdin")
    parser.add_argument("--branches", help="JSON map of branch names to action arrays")
    parser.add_argument("--expected-terminal-digest", help="CAS lease for resume")
    parser.add_argument("--tick", type=int, help="Historical checkpoint tick")
    parser.add_argument("--edits", help="JSON list of transactional source edits")
    parser.add_argument("--revision", help="JSON source revision for verification")
    parser.add_argument("--expected-source-digest", help="CAS lease for source editing")
    parser.add_argument("--choice", choices=("signal", "shelter"), default="signal")
    parser.add_argument("--plan", help="JSON solver plan for verification")
    parser.add_argument("--missions", default=str(DEFAULT_MISSIONS), help="Authored mission board JSON")
    parser.add_argument("--report", help="Portable mission report JSON for replay verification")
    parser.add_argument("--mission-edits", help="Transactional mission edit JSON")
    parser.add_argument("--expected-board-digest", help="Optimistic board revision lease")
    parser.add_argument("--mission-revision", help="Portable mission revision JSON")
    parser.add_argument("--comparison", help="Portable replay-derived mission revision comparison")
    parser.add_argument("--package", help="Portable original game package")
    parser.add_argument("--preview", help="Portable source-bound market preview JSON")
    parser.add_argument("--play", help="Portable gameplay session produced from a package")
    parser.add_argument("--preview-bundle", help="Optional canonical gameplay bundle for edited mission preview")
    parser.add_argument("--require-all", action="store_true", help="Require every authored mission to be earned")
    parser.add_argument("--journal", help="Portable replay journal JSON")
    parser.add_argument("--other-journal", help="Candidate journal for reconciliation")
    parser.add_argument("--expected-journal-digest", help="CAS journal lease")
    parser.add_argument("--revision-index", type=int, help="Historical journal revision")
    parser.add_argument("--goal", help="Route destination as x,y")
    parser.add_argument("--route", help="Portable replay-verified route JSON")
    parser.add_argument("--stops", help="JSON array of route-and-interaction stops")
    parser.add_argument("--itinerary", help="Portable replay-verified itinerary JSON")
    parser.add_argument("--trial", help="Authored time trial course JSON")
    parser.add_argument("--reports", help="JSON array of replay-verified time trial reports")
    parser.add_argument("--board", help="Portable time trial leaderboard JSON")
    parser.add_argument("--season", help="Source-bound authored championship season JSON")
    parser.add_argument("--season-edits", help="Transactional season authoring edits JSON")
    parser.add_argument("--season-revision", help="Replay-verifiable season authoring revision JSON")
    parser.add_argument("--preview-season-record", help="Existing earned season save for edit preview")
    parser.add_argument("--season-record", help="Portable replay-verified season save JSON")
    parser.add_argument("--season-records", help="JSON array of replay-verified season saves")
    parser.add_argument("--season-board", help="Portable replay-verified season standings JSON")
    parser.add_argument("--expected-season-digest", help="CAS lease for season continuation")
    parser.add_argument("--contracts", help="Authored source-bound contract board")
    parser.add_argument("--contract-save", help="Portable replay-verified contract save")
    parser.add_argument("--contract-edits", help="Transactional contract board edits")
    parser.add_argument("--contract-plan", help="Portable replay-verified contract solver plan")
    parser.add_argument("--contract-revision", help="Replay-verifiable contract edit revision")
    parser.add_argument("--expected-contract-digest", help="CAS lease for contract save or board")
    parser.add_argument("--survey-board", help="Authored exploration site board JSON")
    parser.add_argument("--survey-report", help="Portable replay-verified survey report")
    parser.add_argument("--survey-hint", help="Portable NPC-aware survey guidance")
    parser.add_argument("--survey-edits", help="Transactional survey site edits")
    parser.add_argument("--survey-revision", help="Portable survey authoring revision")
    parser.add_argument("--expected-survey-digest", help="CAS lease for survey continuation")
    parser.add_argument("--expected-survey-board-digest", help="CAS lease for survey editor")
    parser.add_argument("--weather-board", help="Authored weather phase and hazard board")
    parser.add_argument("--weather-report", help="Portable weather gameplay report")
    parser.add_argument("--weather-forecast", help="Portable weather forecast")
    parser.add_argument("--weather-edits", help="Transactional weather board edits")
    parser.add_argument("--weather-revision", help="Portable weather authoring revision")
    parser.add_argument("--expected-weather-digest", help="CAS lease for weather continuation")
    parser.add_argument("--expected-weather-board-digest", help="CAS lease for weather authoring")
    parser.add_argument("--horizon", type=int, default=12, help="Bounded weather forecast horizon")
    parser.add_argument("--dialogue-board", help="Authored merchant dialogue board")
    parser.add_argument("--dialogue-report", help="Portable replay-verified dialogue report")
    parser.add_argument("--dialogue-edits", help="Transactional merchant dialogue edits")
    parser.add_argument("--dialogue-revision", help="Portable merchant dialogue revision")
    parser.add_argument("--expected-dialogue-digest", help="CAS lease for dialogue continuation")
    parser.add_argument("--expected-dialogue-board-digest", help="CAS lease for dialogue authoring")
    parser.add_argument("--expedition", help="Portable integrated expedition report")
    parser.add_argument("--expedition-package", help="Portable original expedition package")
    parser.add_argument("--expedition-play", help="Portable replay-verified expedition package play")
    parser.add_argument("--expedition-id", default="lantern_quay_expedition",
                        help="Original authored expedition package identifier")
    parser.add_argument("--expected-expedition-digest", help="CAS lease for expedition continuation")
    parser.add_argument("--expedition-journal", help="Portable append-only expedition journal")
    parser.add_argument("--other-expedition-journal", help="Candidate expedition journal")
    parser.add_argument("--expedition-comparison", help="Portable expedition journal comparison")
    parser.add_argument("--expected-expedition-journal-digest", help="CAS lease for expedition journal")
    parser.add_argument("--quest-board", help="Authored expedition quest/event board")
    parser.add_argument("--quest-report", help="Portable replay-verified quest report")
    parser.add_argument("--quest-edits", help="Transactional quest board edits")
    parser.add_argument("--quest-revision", help="Portable quest authoring revision")
    parser.add_argument("--expected-quest-board-digest", help="CAS lease for quest board")
    parser.add_argument("--ghost-bundle", help="Verified opponent save for ghost racing")
    parser.add_argument("--trial-edits", help="JSON array of transactional time trial edits")
    parser.add_argument("--trial-revision", help="Portable time trial course revision JSON")
    parser.add_argument("--expected-course-digest", help="CAS lease for time trial course")
    parser.add_argument("--max-steps", type=int, default=64, help="Bounded route search horizon")
    parser.add_argument("--convoy-board", default=str(DEFAULT_CONVOY), help="Authored escort route and tactical encounter board")
    parser.add_argument("--convoy-report", help="Portable replay-verified convoy save")
    parser.add_argument("--convoy-edits", help="Transactional convoy board edits")
    parser.add_argument("--convoy-revision", help="Portable replay-verified convoy edit revision")
    parser.add_argument("--expected-convoy-digest", help="CAS lease for convoy continuation")
    parser.add_argument("--expected-convoy-board-digest", help="CAS lease for convoy authoring")
    parser.add_argument("--convoy-package", help="Portable authored convoy game package")
    parser.add_argument("--convoy-play", help="Portable replay-verified convoy package play")
    parser.add_argument("--convoy-package-id", default="lantern_quay_convoy", help="Original package identifier")
    parser.add_argument("--expected-convoy-play-digest", help="CAS lease for portable convoy play")
    parser.add_argument("--convoy-journal", help="Portable append-only convoy journal")
    parser.add_argument("--expected-convoy-journal-digest", help="CAS lease for convoy journal append")
    parser.add_argument("--convoy-revision-index", type=int, help="Historical convoy journal index")
    parser.add_argument("--convoy-plan", help="Replay-verified source-to-victory convoy plan")
    parser.add_argument("--convoy-contracts", help="Authored convoy contract quest board")
    parser.add_argument("--convoy-contract-report", help="Replay-verified convoy contract result")
    parser.add_argument("--convoy-contract-edits", help="Transactional convoy quest edits")
    parser.add_argument("--convoy-contract-revision", help="Portable convoy quest edit revision")
    parser.add_argument("--expected-convoy-contract-digest", help="CAS lease for convoy quest board")
    parser.add_argument("--convoy-choice", choices=("relief", "salvage"), default="relief")
    parser.add_argument("--convoy-acceptance", help="Portable original game acceptance receipt")
    parser.add_argument("--league-board", help="Authored convoy league championship")
    parser.add_argument("--league-save", help="Portable replay-verified league save")
    parser.add_argument("--league-package", help="Portable original convoy league package")
    parser.add_argument("--league-play", help="Portable replay-verified league package play")
    parser.add_argument("--league-edits", help="Transactional championship board edits")
    parser.add_argument("--league-revision", help="Portable replay-verified league authoring revision")
    parser.add_argument("--sessions", help="JSON list of player action arrays by round")
    parser.add_argument("--expected-league-digest", help="CAS lease for league save")
    parser.add_argument("--expected-league-play-digest", help="CAS lease for league package play")
    parser.add_argument("--expected-league-board-digest", help="CAS lease for league editor")
    parser.add_argument("--league-package-id", default="lantern_quay_league")
    parser.add_argument("--league-plan", help="Replay-verified championship solver plan")
    parser.add_argument("--league-journal", help="Append-only championship journal")
    parser.add_argument("--other-league-journal", help="Candidate league journal for comparison")
    parser.add_argument("--expected-league-journal-digest", help="CAS lease for league journal")
    parser.add_argument("--league-journal-index", type=int, help="Historical league journal index")
    parser.add_argument("--entrants", help="JSON list of entrant IDs and verified league saves")
    parser.add_argument("--league-board-report", help="Portable replay-verified championship ranking")
    parser.add_argument("--league-acceptance", help="Source-to-victory league acceptance receipt")
    parser.add_argument("--league-contracts", help="Authored round contract quest boards")
    parser.add_argument("--league-choices", help="Relief or salvage choice per played round")
    parser.add_argument("--league-consequences", help="Replay-verified earned consequence report")
    parser.add_argument("--league-choice-package", help="Portable source-bound choice package")
    parser.add_argument("--league-choice-play", help="Portable replay-verified choice package play")
    parser.add_argument("--league-hint", help="Portable replay-verified league action guidance")
    parser.add_argument("--league-quest-board", help="Authored cross-round quest DAG")
    parser.add_argument("--league-quest-report", help="Replay-verified cross-round mission report")
    parser.add_argument("--league-quest-edits", help="Transactional quest DAG edits")
    parser.add_argument("--league-quest-revision", help="Portable replay-verified quest revision")
    parser.add_argument("--expected-league-quest-board-digest", help="CAS lease for quest authoring")
    parser.add_argument("--league-quest-preview", action="store_true", help="Replay source-bound edit preview")
    parser.add_argument("--require-win", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "league-quests":
            output = build_league_quest_report(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                _required_json(args.league_quest_board, "league-quest-board", MAX_LEAGUE_QUEST_BOARD_BYTES),
                require_all=args.require_all)
        elif args.command == "league-verify-quests":
            output = verify_league_quest_report(
                _required_json(args.league_quest_report, "league-quest-report", MAX_LEAGUE_QUEST_REPORT_BYTES),
                require_all=args.require_all)
        elif args.command == "league-quest-status":
            output = league_quest_status(
                _required_json(args.league_quest_report, "league-quest-report", MAX_LEAGUE_QUEST_REPORT_BYTES))
        elif args.command == "league-quest-author":
            if not args.expected_league_quest_board_digest:
                raise HarborError("--expected-league-quest-board-digest is required")
            output = edit_league_quests(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                _required_json(args.league_quest_board, "league-quest-board", MAX_LEAGUE_QUEST_BOARD_BYTES),
                _required_json(args.league_quest_edits, "league-quest-edits", MAX_LEAGUE_QUEST_BOARD_BYTES),
                expected_digest=args.expected_league_quest_board_digest,
                preview=args.league_quest_preview)
        elif args.command == "league-verify-quest-author":
            output = verify_league_quest_revision(
                _required_json(args.league_quest_revision, "league-quest-revision", MAX_LEAGUE_QUEST_REVISION_BYTES))
        elif args.command == "league-hint":
            output = build_league_guidance(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES))
        elif args.command == "league-verify-hint":
            output = verify_league_guidance(
                _required_json(args.league_hint, "league-hint", MAX_LEAGUE_GUIDANCE_BYTES))
        elif args.command == "league-consequences":
            output = build_league_consequences(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                _required_json(args.league_contracts, "league-contracts", MAX_LEAGUE_BYTES),
                _required_json(args.league_choices, "league-choices"),
                require_all=args.require_all)
        elif args.command == "league-verify-consequences":
            output = verify_league_consequences(
                _required_json(args.league_consequences, "league-consequences", MAX_LEAGUE_CONSEQUENCE_BYTES),
                require_all=args.require_all)
        elif args.command == "league-choice-compare":
            output = compare_league_choices(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                _required_json(args.league_contracts, "league-contracts", MAX_LEAGUE_BYTES))
        elif args.command == "league-choice-package":
            output = build_choice_package(
                args.league_package_id,
                _required_json(args.league_package, "league-package", MAX_LEAGUE_PACKAGE_BYTES),
                _required_json(args.league_contracts, "league-contracts", MAX_LEAGUE_BYTES))
        elif args.command == "league-choice-verify-package":
            output = verify_choice_package(
                _required_json(args.league_choice_package, "league-choice-package", MAX_LEAGUE_CHOICE_PACKAGE_BYTES))
        elif args.command == "league-choice-play":
            output = play_choice_package(
                _required_json(args.league_choice_package, "league-choice-package", MAX_LEAGUE_CHOICE_PACKAGE_BYTES),
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                _required_json(args.league_choices, "league-choices"),
                require_all=args.require_all)
        elif args.command == "league-choice-verify-play":
            output = verify_choice_package_play(
                _required_json(args.league_choice_play, "league-choice-play", MAX_LEAGUE_CHOICE_PLAY_BYTES),
                require_all=args.require_all)
        elif args.command == "league-solve":
            output = solve_league(
                load_source(Path(args.source)),
                _required_json(args.league_board, "league-board", MAX_LEAGUE_BYTES))
        elif args.command == "league-verify-plan":
            output = verify_league_plan(
                _required_json(args.league_plan, "league-plan", MAX_LEAGUE_PLAN_BYTES))
        elif args.command == "league-accept":
            output = accept_league(
                load_source(Path(args.source)),
                _required_json(args.league_board, "league-board", MAX_LEAGUE_BYTES))
        elif args.command == "league-verify-accept":
            output = verify_league_acceptance(
                _required_json(args.league_acceptance, "league-acceptance", MAX_LEAGUE_ACCEPT_BYTES))
        elif args.command == "league-journal-init":
            output = create_league_journal(
                _required_json(args.league_package, "league-package", MAX_LEAGUE_PACKAGE_BYTES))
        elif args.command == "league-journal-verify":
            output = verify_league_journal(
                _required_json(args.league_journal, "league-journal", MAX_LEAGUE_JOURNAL_BYTES))
        elif args.command == "league-journal-append":
            if not args.expected_league_journal_digest:
                raise HarborError("--expected-league-journal-digest is required")
            output = append_league_journal(
                _required_json(args.league_journal, "league-journal", MAX_LEAGUE_JOURNAL_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_league_journal_digest)
        elif args.command == "league-journal-at":
            if args.league_journal_index is None:
                raise HarborError("--league-journal-index is required")
            output = league_journal_at(
                _required_json(args.league_journal, "league-journal", MAX_LEAGUE_JOURNAL_BYTES),
                args.league_journal_index)
        elif args.command == "league-journal-compare":
            output = compare_league_journals(
                _required_json(args.league_journal, "league-journal", MAX_LEAGUE_JOURNAL_BYTES),
                _required_json(args.other_league_journal, "other-league-journal", MAX_LEAGUE_JOURNAL_BYTES))
        elif args.command == "league-journal-fast-forward":
            if not args.expected_league_journal_digest:
                raise HarborError("--expected-league-journal-digest is required")
            output = fast_forward_league_journal(
                _required_json(args.league_journal, "league-journal", MAX_LEAGUE_JOURNAL_BYTES),
                _required_json(args.other_league_journal, "other-league-journal", MAX_LEAGUE_JOURNAL_BYTES),
                expected_digest=args.expected_league_journal_digest)
        elif args.command == "league-board":
            output = build_league_leaderboard(
                _required_json(args.entrants, "entrants", MAX_LEAGUE_BOARD_BYTES))
        elif args.command == "league-board-verify":
            output = verify_league_leaderboard(
                _required_json(args.league_board_report, "league-board-report", MAX_LEAGUE_BOARD_BYTES))
        elif args.command in ("league-init", "league-run", "league-live", "league-package-build"):
            source = load_source(Path(args.source))
            league = _required_json(args.league_board, "league-board", MAX_LEAGUE_BYTES)
            if args.command == "league-init":
                output = build_league(source, league, [])
            elif args.command == "league-run":
                output = build_league(source, league,
                    _required_json(args.sessions, "sessions", MAX_LEAGUE_SAVE_BYTES),
                    require_complete=args.require_all)
            elif args.command == "league-live":
                output = play_league_live(source, league, instream=sys.stdin, outstream=sys.stderr)
                if args.require_all:
                    verify_league(output, require_complete=True)
            else:
                output = build_league_package(args.league_package_id, source, league)
        elif args.command == "league-verify":
            output = verify_league(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                require_complete=args.require_all)
        elif args.command == "league-status":
            output = league_status(_required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES))
        elif args.command == "league-resume":
            if not args.expected_league_digest:
                raise HarborError("--expected-league-digest is required")
            output = resume_league(
                _required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_league_digest, require_complete=args.require_all)
        elif args.command == "league-package-verify":
            output = verify_league_package(
                _required_json(args.league_package, "league-package", MAX_LEAGUE_PACKAGE_BYTES))
        elif args.command == "league-package-play":
            output = play_league_package(
                _required_json(args.league_package, "league-package", MAX_LEAGUE_PACKAGE_BYTES),
                _required_json(args.sessions, "sessions", MAX_LEAGUE_SAVE_BYTES),
                require_complete=args.require_all)
        elif args.command == "league-package-verify-play":
            output = verify_league_package_play(
                _required_json(args.league_play, "league-play", MAX_LEAGUE_PLAY_BYTES),
                require_complete=args.require_all)
        elif args.command == "league-package-resume":
            if not args.expected_league_play_digest:
                raise HarborError("--expected-league-play-digest is required")
            output = resume_league_package(
                _required_json(args.league_play, "league-play", MAX_LEAGUE_PLAY_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_league_play_digest,
                require_complete=args.require_all)
        elif args.command == "league-author":
            if not args.expected_league_board_digest:
                raise HarborError("--expected-league-board-digest is required")
            output = edit_league(
                load_source(Path(args.source)),
                _required_json(args.league_board, "league-board", MAX_LEAGUE_BYTES),
                _required_json(args.league_edits, "league-edits", MAX_LEAGUE_BYTES),
                expected_digest=args.expected_league_board_digest,
                preview_save=(_required_json(args.league_save, "league-save", MAX_LEAGUE_SAVE_BYTES)
                              if args.league_save else None))
        elif args.command == "league-verify-author":
            output = verify_league_revision(
                _required_json(args.league_revision, "league-revision", MAX_LEAGUE_REVISION_BYTES))
        elif args.command == "convoy-accept":
            output = accept_convoy(
                load_source(Path(args.source)),
                _required_json(args.convoy_board, "convoy-board", MAX_CONVOY_BOARD_BYTES),
                _required_json(
                    args.convoy_contracts or str(
                        Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay_convoy_contracts.json"
                    ),
                    "convoy-contracts", MAX_CONVOY_CONTRACT_BOARD_BYTES,
                ),
            )
        elif args.command == "convoy-verify-accept":
            output = verify_convoy_acceptance(
                _required_json(args.convoy_acceptance, "convoy-acceptance", MAX_CONVOY_ACCEPT_BYTES),
            )
        elif args.command == "convoy-contract-run":
            output = build_convoy_contract_report(
                _required_json(args.convoy_report, "convoy-report", MAX_CONVOY_REPORT_BYTES),
                _required_json(args.convoy_contracts, "convoy-contracts", MAX_CONVOY_CONTRACT_BOARD_BYTES),
                choice=args.convoy_choice, require_all=args.require_all,
            )
        elif args.command == "convoy-contract-verify":
            output = {"verified": True, **verify_convoy_contract_report(
                _required_json(args.convoy_contract_report, "convoy-contract-report", MAX_CONVOY_CONTRACT_REPORT_BYTES),
                require_all=args.require_all,
            )}
        elif args.command == "convoy-contract-status":
            output = convoy_contract_status(
                _required_json(args.convoy_contract_report, "convoy-contract-report", MAX_CONVOY_CONTRACT_REPORT_BYTES),
            )
        elif args.command == "convoy-contract-author":
            if not args.expected_convoy_contract_digest:
                raise HarborError("--expected-convoy-contract-digest is required")
            output = edit_convoy_contracts(
                _required_json(args.convoy_report, "convoy-report", MAX_CONVOY_REPORT_BYTES),
                _required_json(args.convoy_contracts, "convoy-contracts", MAX_CONVOY_CONTRACT_BOARD_BYTES),
                _required_json(args.convoy_contract_edits, "convoy-contract-edits"),
                expected_board_digest=args.expected_convoy_contract_digest,
                preview_report=(
                    _required_json(args.convoy_contract_report, "convoy-contract-report", MAX_CONVOY_CONTRACT_REPORT_BYTES)
                    if args.convoy_contract_report else None
                ),
            )
        elif args.command == "convoy-contract-verify-author":
            output = verify_convoy_contract_revision(
                _required_json(args.convoy_contract_revision, "convoy-contract-revision", MAX_CONVOY_CONTRACT_REVISION_BYTES),
            )
        elif args.command == "convoy-solve":
            output = solve_convoy(
                load_source(Path(args.source)),
                _required_json(args.convoy_board, "convoy-board", MAX_CONVOY_BOARD_BYTES),
            )
        elif args.command == "convoy-verify-plan":
            output = verify_convoy_plan(
                _required_json(args.convoy_plan, "convoy-plan", MAX_CONVOY_PLAN_BYTES),
            )
        elif args.command == "convoy-package-build":
            output = build_convoy_package(
                args.convoy_package_id, load_source(Path(args.source)),
                _required_json(args.convoy_board, "convoy-board", MAX_CONVOY_BOARD_BYTES),
            )
        elif args.command == "convoy-package-verify":
            output = {"verified": True, **verify_convoy_package(
                _required_json(args.convoy_package, "convoy-package", MAX_CONVOY_PACKAGE_BYTES),
            )}
        elif args.command == "convoy-package-play":
            output = play_convoy_package(
                _required_json(args.convoy_package, "convoy-package", MAX_CONVOY_PACKAGE_BYTES),
                _required_json(args.actions, "actions"),
                require_complete=args.require_all,
            )
        elif args.command == "convoy-package-verify-play":
            output = verify_convoy_package_play(
                _required_json(args.convoy_play, "convoy-play", MAX_CONVOY_PLAY_BYTES),
                require_complete=args.require_all,
            )
        elif args.command == "convoy-package-resume":
            if not args.expected_convoy_play_digest:
                raise HarborError("--expected-convoy-play-digest is required")
            output = resume_convoy_package(
                _required_json(args.convoy_play, "convoy-play", MAX_CONVOY_PLAY_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_convoy_play_digest,
                require_complete=args.require_all,
            )
        elif args.command == "convoy-journal-init":
            output = create_convoy_journal(
                _required_json(args.convoy_package, "convoy-package", MAX_CONVOY_PACKAGE_BYTES),
            )
        elif args.command == "convoy-journal-verify":
            output = verify_convoy_journal(
                _required_json(args.convoy_journal, "convoy-journal", MAX_CONVOY_JOURNAL_BYTES),
            )
        elif args.command == "convoy-journal-append":
            if not args.expected_convoy_journal_digest:
                raise HarborError("--expected-convoy-journal-digest is required")
            output = append_convoy_journal(
                _required_json(args.convoy_journal, "convoy-journal", MAX_CONVOY_JOURNAL_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_convoy_journal_digest,
            )
        elif args.command == "convoy-journal-at":
            if args.convoy_revision_index is None:
                raise HarborError("--convoy-revision-index is required")
            output = convoy_journal_at(
                _required_json(args.convoy_journal, "convoy-journal", MAX_CONVOY_JOURNAL_BYTES),
                args.convoy_revision_index,
            )
        elif args.command == "convoy-run":
            output = build_convoy(
                load_source(Path(args.source)),
                _required_json(args.convoy_board, "convoy-board", MAX_CONVOY_BOARD_BYTES),
                _required_json(args.actions, "actions"),
                require_complete=args.require_all,
            )
        elif args.command == "convoy-live":
            output = play_convoy_live(
                load_source(Path(args.source)),
                _required_json(args.convoy_board, "convoy-board", MAX_CONVOY_BOARD_BYTES),
                instream=sys.stdin, outstream=sys.stderr,
            )
            if args.require_all:
                verify_convoy(output, require_complete=True)
        elif args.command == "convoy-verify":
            output = {"verified": True, **verify_convoy(
                _required_json(args.convoy_report, "convoy-report", MAX_CONVOY_REPORT_BYTES),
                require_complete=args.require_all,
            )}
        elif args.command == "convoy-status":
            output = convoy_status(
                _required_json(args.convoy_report, "convoy-report", MAX_CONVOY_REPORT_BYTES),
            )
        elif args.command == "convoy-resume":
            if not args.expected_convoy_digest:
                raise HarborError("--expected-convoy-digest is required")
            output = resume_convoy(
                _required_json(args.convoy_report, "convoy-report", MAX_CONVOY_REPORT_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_convoy_digest,
                require_complete=args.require_all,
            )
        elif args.command == "convoy-author":
            if not args.expected_convoy_board_digest:
                raise HarborError("--expected-convoy-board-digest is required")
            output = edit_convoy_board(
                load_source(Path(args.source)),
                _required_json(args.convoy_board, "convoy-board", MAX_CONVOY_BOARD_BYTES),
                _required_json(args.convoy_edits, "convoy-edits"),
                expected_board_digest=args.expected_convoy_board_digest,
                preview_report=(
                    _required_json(args.convoy_report, "convoy-report", MAX_CONVOY_REPORT_BYTES)
                    if args.convoy_report else None
                ),
            )
        elif args.command == "convoy-verify-author":
            output = verify_convoy_revision(
                _required_json(args.convoy_revision, "convoy-revision", MAX_CONVOY_REVISION_BYTES),
            )
        elif args.command == "quest-run":
            output = build_quest_report(
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES),
                _required_json(args.quest_board, "quest-board", MAX_QUEST_BOARD_BYTES),
                require_all=args.require_all,
            )
        elif args.command == "quest-verify":
            output = {"verified": True, **verify_quest_report(
                _required_json(args.quest_report, "quest-report", MAX_QUEST_REPORT_BYTES),
                require_all=args.require_all,
            )}
        elif args.command == "quest-status":
            output = quest_status(
                _required_json(args.quest_report, "quest-report", MAX_QUEST_REPORT_BYTES))
        elif args.command == "quest-author":
            if not args.expected_expedition_digest or not args.expected_quest_board_digest:
                raise HarborError("quest authoring expedition and board leases required")
            output = edit_quest_board(
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES),
                _required_json(args.quest_board, "quest-board", MAX_QUEST_BOARD_BYTES),
                _required_json(args.quest_edits, "quest-edits", MAX_QUEST_BOARD_BYTES),
                expected_expedition_digest=args.expected_expedition_digest,
                expected_board_digest=args.expected_quest_board_digest,
                preview_report=_required_json(
                    args.quest_report, "quest-report", MAX_QUEST_REPORT_BYTES
                ) if args.quest_report else None,
            )
        elif args.command == "quest-verify-author":
            output = {"verified": True, **verify_quest_edit(
                _required_json(args.quest_revision, "quest-revision", MAX_QUEST_REVISION_BYTES))}
        elif args.command == "expedition-journal-init":
            output = create_expedition_journal(
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES))
        elif args.command == "expedition-journal-verify":
            output = {"verified": True, **verify_expedition_journal(
                _required_json(args.expedition_journal, "expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES))}
        elif args.command == "expedition-journal-append":
            if not args.expected_expedition_journal_digest:
                raise HarborError("--expected-expedition-journal-digest is required")
            output = append_expedition_journal(
                _required_json(args.expedition_journal, "expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES),
                expected_digest=args.expected_expedition_journal_digest,
            )
        elif args.command == "expedition-journal-at":
            if args.revision_index is None:
                raise HarborError("--revision-index is required")
            output = expedition_journal_at(
                _required_json(args.expedition_journal, "expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
                args.revision_index,
            )
        elif args.command == "expedition-journal-fork":
            if args.revision_index is None or not args.expected_expedition_journal_digest:
                raise HarborError("--revision-index and --expected-expedition-journal-digest are required")
            output = fork_expedition_journal(
                _required_json(args.expedition_journal, "expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
                args.revision_index, expected_digest=args.expected_expedition_journal_digest,
            )
        elif args.command == "expedition-journal-compare":
            output = compare_expedition_journals(
                _required_json(args.expedition_journal, "expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
                _required_json(args.other_expedition_journal, "other-expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
            )
        elif args.command == "expedition-journal-verify-comparison":
            output = {"verified": True, **verify_expedition_comparison(
                _required_json(args.expedition_comparison, "expedition-comparison", MAX_EXPEDITION_COMPARE_BYTES))}
        elif args.command == "expedition-journal-fast-forward":
            if not args.expected_expedition_journal_digest:
                raise HarborError("--expected-expedition-journal-digest is required")
            output = fast_forward_expedition_journal(
                _required_json(args.expedition_journal, "expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
                _required_json(args.other_expedition_journal, "other-expedition-journal", MAX_EXPEDITION_JOURNAL_BYTES),
                expected_digest=args.expected_expedition_journal_digest,
            )
        elif args.command == "expedition-live":
            return play_expedition_live(
                load_source(Path(args.source)),
                _required_json(args.survey_board, "survey-board", MAX_SURVEY_BOARD_BYTES),
                _required_json(args.weather_board, "weather-board", MAX_WEATHER_BOARD_BYTES),
                _required_json(args.dialogue_board, "dialogue-board", MAX_DIALOGUE_BOARD_BYTES),
                sys.stdin, sys.stdout,
                root=_required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES)
                if args.expedition else None,
                expected_digest=args.expected_expedition_digest,
            )
        elif args.command == "expedition-build":
            output = build_expedition_package(
                args.expedition_id, load_source(Path(args.source)),
                _required_json(args.survey_board, "survey-board", MAX_SURVEY_BOARD_BYTES),
                _required_json(args.weather_board, "weather-board", MAX_WEATHER_BOARD_BYTES),
                _required_json(args.dialogue_board, "dialogue-board", MAX_DIALOGUE_BOARD_BYTES),
            )
        elif args.command == "expedition-verify-package":
            output = {"verified": True, **verify_expedition_package(
                _required_json(args.expedition_package, "expedition-package", MAX_EXPEDITION_PACKAGE_BYTES))}
        elif args.command == "expedition-play":
            output = play_expedition_package(
                _required_json(args.expedition_package, "expedition-package", MAX_EXPEDITION_PACKAGE_BYTES),
                _required_json(args.actions, "actions"),
                require_complete=args.require_all,
            )
        elif args.command == "expedition-verify-play":
            output = {"verified": True, **verify_expedition_package_play(
                _required_json(args.expedition_play, "expedition-play", MAX_EXPEDITION_PLAY_BYTES),
                require_complete=args.require_all,
            )}
        elif args.command == "expedition-run":
            output = build_expedition(
                load_source(Path(args.source)),
                _required_json(args.survey_board, "survey-board", MAX_SURVEY_BOARD_BYTES),
                _required_json(args.weather_board, "weather-board", MAX_WEATHER_BOARD_BYTES),
                _required_json(args.dialogue_board, "dialogue-board", MAX_DIALOGUE_BOARD_BYTES),
                _required_json(args.actions, "actions"),
                require_complete=args.require_all,
            )
        elif args.command == "expedition-verify":
            output = {"verified": True, **verify_expedition(
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES),
                require_complete=args.require_all,
            )}
        elif args.command == "expedition-resume":
            if not args.expected_expedition_digest:
                raise HarborError("--expected-expedition-digest is required")
            output = resume_expedition(
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_expedition_digest,
                require_complete=args.require_all,
            )
        elif args.command == "expedition-status":
            output = expedition_status(
                _required_json(args.expedition, "expedition", MAX_EXPEDITION_REPORT_BYTES))
        elif args.command == "dialogue-run":
            output = build_dialogue_game(
                load_source(Path(args.source)),
                _required_json(args.dialogue_board, "dialogue-board", MAX_DIALOGUE_BOARD_BYTES),
                _required_json(args.actions, "actions"),
                require_win=args.require_win,
            )
        elif args.command == "dialogue-verify":
            output = {"verified": True, **verify_dialogue_game(
                _required_json(args.dialogue_report, "dialogue-report", MAX_DIALOGUE_REPORT_BYTES),
                require_win=args.require_win,
            )}
        elif args.command == "dialogue-resume":
            if not args.expected_dialogue_digest:
                raise HarborError("--expected-dialogue-digest is required")
            output = resume_dialogue_game(
                _required_json(args.dialogue_report, "dialogue-report", MAX_DIALOGUE_REPORT_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_dialogue_digest,
                require_win=args.require_win,
            )
        elif args.command == "dialogue-author":
            if not args.expected_source_digest or not args.expected_dialogue_board_digest:
                raise HarborError("dialogue authoring source and board leases required")
            output = edit_dialogue(
                load_source(Path(args.source)),
                _required_json(args.dialogue_board, "dialogue-board", MAX_DIALOGUE_BOARD_BYTES),
                _required_json(args.dialogue_edits, "dialogue-edits", MAX_DIALOGUE_BOARD_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_board_digest=args.expected_dialogue_board_digest,
                preview_report=_required_json(
                    args.dialogue_report, "dialogue-report", MAX_DIALOGUE_REPORT_BYTES
                ) if args.dialogue_report else None,
            )
        elif args.command == "dialogue-verify-author":
            output = {"verified": True, **verify_dialogue_edit(
                _required_json(args.dialogue_revision, "dialogue-revision", MAX_DIALOGUE_REVISION_BYTES))}
        elif args.command == "weather-run":
            output = build_weather_game(
                load_source(Path(args.source)),
                _required_json(args.weather_board, "weather-board", MAX_WEATHER_BOARD_BYTES),
                _required_json(args.actions, "actions"),
                require_win=args.require_win,
            )
        elif args.command == "weather-verify":
            output = {"verified": True, **verify_weather_game(
                _required_json(args.weather_report, "weather-report", MAX_WEATHER_REPORT_BYTES),
                require_win=args.require_win,
            )}
        elif args.command == "weather-resume":
            if not args.expected_weather_digest:
                raise HarborError("--expected-weather-digest is required")
            output = resume_weather_game(
                _required_json(args.weather_report, "weather-report", MAX_WEATHER_REPORT_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_weather_digest,
                require_win=args.require_win,
            )
        elif args.command == "weather-forecast":
            output = weather_forecast(
                _required_json(args.weather_report, "weather-report", MAX_WEATHER_REPORT_BYTES),
                horizon=args.horizon,
            )
        elif args.command == "weather-verify-forecast":
            output = {"verified": True, **verify_weather_forecast(
                _required_json(args.weather_forecast, "weather-forecast", MAX_WEATHER_FORECAST_BYTES))}
        elif args.command == "weather-author":
            if not args.expected_source_digest or not args.expected_weather_board_digest:
                raise HarborError("weather authoring source and board leases required")
            output = edit_weather(
                load_source(Path(args.source)),
                _required_json(args.weather_board, "weather-board", MAX_WEATHER_BOARD_BYTES),
                _required_json(args.weather_edits, "weather-edits", MAX_WEATHER_BOARD_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_board_digest=args.expected_weather_board_digest,
                preview_report=_required_json(
                    args.weather_report, "weather-report", MAX_WEATHER_REPORT_BYTES
                ) if args.weather_report else None,
            )
        elif args.command == "weather-verify-author":
            output = {"verified": True, **verify_weather_edit(
                _required_json(args.weather_revision, "weather-revision", MAX_WEATHER_REVISION_BYTES))}
        elif args.command == "survey-run":
            output = build_survey(
                load_source(Path(args.source)),
                _required_json(args.survey_board, "survey-board", MAX_SURVEY_BOARD_BYTES),
                _required_json(args.actions, "actions"),
                require_complete=args.require_all,
            )
        elif args.command == "survey-verify":
            output = {"verified": True, **verify_survey(
                _required_json(args.survey_report, "survey-report", MAX_SURVEY_REPORT_BYTES),
                require_complete=args.require_all,
            )}
        elif args.command == "survey-resume":
            if not args.expected_survey_digest:
                raise HarborError("--expected-survey-digest is required")
            output = resume_survey(
                _required_json(args.survey_report, "survey-report", MAX_SURVEY_REPORT_BYTES),
                _required_json(args.actions, "actions"),
                expected_digest=args.expected_survey_digest,
                require_complete=args.require_all,
            )
        elif args.command == "survey-hint":
            output = survey_hint(
                _required_json(args.survey_report, "survey-report", MAX_SURVEY_REPORT_BYTES),
                max_steps=args.max_steps,
            )
        elif args.command == "survey-verify-hint":
            output = {"verified": True, **verify_survey_hint(
                _required_json(args.survey_hint, "survey-hint", MAX_SURVEY_HINT_BYTES))}
        elif args.command == "survey-author":
            if not args.expected_source_digest or not args.expected_survey_board_digest:
                raise HarborError("survey authoring source and board leases required")
            output = edit_survey(
                load_source(Path(args.source)),
                _required_json(args.survey_board, "survey-board", MAX_SURVEY_BOARD_BYTES),
                _required_json(args.survey_edits, "survey-edits", MAX_SURVEY_BOARD_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_board_digest=args.expected_survey_board_digest,
                preview_report=_required_json(
                    args.survey_report, "survey-report", MAX_SURVEY_REPORT_BYTES
                ) if args.survey_report else None,
            )
        elif args.command == "survey-verify-author":
            output = {"verified": True, **verify_survey_edit(
                _required_json(args.survey_revision, "survey-revision", MAX_SURVEY_REVISION_BYTES))}
        elif args.command == "contract-plan":
            output = solve_contract(
                _required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES))
        elif args.command == "contract-verify-plan":
            output = {"verified": True, **verify_contract_plan(
                _required_json(args.contract_plan, "contract-plan", MAX_CONTRACT_PLAN_BYTES))}
        elif args.command == "contract-live":
            save = _required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES)
            if not args.expected_contract_digest or args.expected_contract_digest != save.get("save_digest"):
                raise HarborError("stale contract live checkpoint")
            return play_live(save["source"], sys.stdin, sys.stdout, contract_save=save)
        elif args.command == "contract-init":
            output = build_save(load_source(Path(args.source)),
                _required_json(args.contracts, "contracts", MAX_CONTRACT_BOARD_BYTES), [])
        elif args.command == "contract-next":
            output = next_order(_required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES))
        elif args.command == "contract-verify":
            output = {"verified": True, **verify_save(
                _required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES))}
        elif args.command in ("contract-play", "contract-append"):
            if not args.expected_contract_digest:
                raise HarborError("--expected-contract-digest is required")
            save = _required_json(args.contract_save, "contract-save", MAX_CONTRACT_SAVE_BYTES)
            if args.command == "contract-play":
                output = play_save(save, _required_json(args.actions, "actions"),
                    expected_digest=args.expected_contract_digest)
            else:
                output = append_save(save, _required_json(args.bundle, "bundle"),
                    expected_digest=args.expected_contract_digest)
        elif args.command == "contract-author":
            if not args.expected_source_digest or not args.expected_contract_digest:
                raise HarborError("--expected-source-digest and --expected-contract-digest are required")
            output = edit_board(load_source(Path(args.source)),
                _required_json(args.contracts, "contracts", MAX_CONTRACT_BOARD_BYTES),
                _required_json(args.contract_edits, "contract-edits", MAX_CONTRACT_BOARD_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_board_digest=args.expected_contract_digest)
        elif args.command == "contract-verify-author":
            output = {"verified": True, **verify_edit(
                _required_json(args.contract_revision, "contract-revision", MAX_CONTRACT_EDITS_BYTES))}
        elif args.command in ("season-next", "season-live"):
            next_round = next_season_round(
                _required_json(args.season_record, "season-record", MAX_SEASON_RECORD_BYTES))
            if args.command == "season-live":
                if next_round["status"] != "ready":
                    raise HarborError("season already complete")
                return play_live(
                    next_round["source"], sys.stdin, sys.stdout,
                    course=next_round["round"]["course"],
                )
            output = next_round
        elif args.command == "season-author":
            if not args.expected_source_digest or not args.expected_season_digest:
                raise HarborError("--expected-source-digest and --expected-season-digest are required")
            output = author_season_revision(
                load_source(Path(args.source)),
                _required_json(args.season, "season", MAX_SEASON_BYTES),
                _required_json(args.season_edits, "season-edits", MAX_SEASON_BYTES),
                expected_source_digest=args.expected_source_digest,
                expected_season_digest=args.expected_season_digest,
                preview_record=_required_json(
                    args.preview_season_record, "preview-season-record", MAX_SEASON_RECORD_BYTES
                ) if args.preview_season_record else None,
            )
        elif args.command == "season-verify-author":
            output = {"verified": True, **verify_season_revision(
                _required_json(args.season_revision, "season-revision", MAX_SEASON_REVISION_BYTES))}
        elif args.command == "season-init":
            output = build_season(
                load_source(Path(args.source)),
                _required_json(args.season, "season", MAX_SEASON_BYTES), [],
            )
        elif args.command == "season-append":
            if not args.expected_season_digest:
                raise HarborError("--expected-season-digest is required")
            output = append_season(
                _required_json(args.season_record, "season-record", MAX_SEASON_RECORD_BYTES),
                _required_json(args.bundle, "bundle"),
                expected_record_digest=args.expected_season_digest,
            )
        elif args.command == "season-verify":
            output = {"verified": True, **verify_season_record(
                _required_json(args.season_record, "season-record", MAX_SEASON_RECORD_BYTES))}
        elif args.command == "season-board":
            output = season_board(
                _required_json(args.season_records, "season-records", MAX_SEASON_BOARD_BYTES))
        elif args.command == "season-board-verify":
            output = {"verified": True, "ranking": verify_season_board(
                _required_json(args.season_board, "season-board", MAX_SEASON_BOARD_BYTES))}
        elif args.command == "ghost-race":
            output = ghost_race(
                _required_json(args.bundle, "bundle"),
                _required_json(args.ghost_bundle, "ghost-bundle"),
                _required_json(args.trial, "trial"),
                expected_player_terminal_digest=args.expected_terminal_digest,
            )
        elif args.command == "ghost-verify":
            output = {"verified": True, **verify_ghost_race(
                _required_json(args.report, "report", MAX_GHOST_RACE_BYTES))}
        elif args.command == "trial-author":
            if not args.expected_course_digest or not args.expected_source_digest:
                raise HarborError("--expected-course-digest and --expected-source-digest are required")
            output = author_time_trial_revision(
                _required_json(args.trial, "trial"), load_source(Path(args.source)),
                _required_json(args.trial_edits, "trial-edits"),
                expected_course_digest=args.expected_course_digest,
                expected_source_digest=args.expected_source_digest,
                preview_bundle=_required_json(args.preview_bundle, "preview-bundle")
                if args.preview_bundle else None,
            )
        elif args.command == "trial-verify-author":
            output = {"verified": True, **verify_time_trial_revision(
                _required_json(args.trial_revision, "trial-revision", MAX_TRIAL_REVISION_BYTES))}
        elif args.command == "trial-run":
            output = time_trial_report(
                _required_json(args.bundle, "bundle"),
                _required_json(args.trial, "trial"),
                require_finish=args.require_win,
            )
        elif args.command == "trial-verify":
            output = {"verified": True, **verify_time_trial_report(
                _required_json(args.report, "report", MAX_TRIAL_REPORT_BYTES),
                require_finish=args.require_win,
            )}
        elif args.command == "trial-resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required")
            output = resume_time_trial(
                _required_json(args.bundle, "bundle"),
                _required_json(args.trial, "trial"),
                _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest,
                require_finish=args.require_win,
            )
        elif args.command == "trial-leaderboard":
            output = time_trial_leaderboard(
                _required_json(args.reports, "reports", MAX_TRIAL_BOARD_BYTES))
        elif args.command == "trial-verify-leaderboard":
            output = {"verified": True, "ranking": verify_time_trial_leaderboard(
                _required_json(args.board, "board", MAX_TRIAL_BOARD_BYTES))}
        elif args.command == "itinerary-build":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required")
            output = build_itinerary(
                _required_json(args.bundle, "bundle"),
                _required_json(args.stops, "stops"),
                expected_terminal_digest=args.expected_terminal_digest,
                max_steps=args.max_steps,
            )
        elif args.command == "itinerary-verify":
            output = {"verified": True, **verify_itinerary(
                _required_json(args.itinerary, "itinerary", MAX_ITINERARY_BYTES))}
        elif args.command == "route-plan":
            if not args.goal or not args.expected_terminal_digest:
                raise HarborError("--goal and --expected-terminal-digest are required")
            coordinates = args.goal.split(",")
            if len(coordinates) != 2 or any(not part.isascii() or not part.isdecimal() for part in coordinates):
                raise HarborError("--goal must be x,y")
            output = plan_route(
                _required_json(args.bundle, "bundle"),
                [int(part) for part in coordinates],
                expected_terminal_digest=args.expected_terminal_digest,
                max_steps=args.max_steps,
            )
        elif args.command == "route-verify":
            output = {"verified": True, **verify_route(
                _required_json(args.route, "route", MAX_ROUTE_BYTES))}
        elif args.command == "journal-package-play":
            output = export_journal_package_play(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.package, "package", MAX_PACKAGE_BYTES),
                require_all=args.require_all,
            )
        elif args.command == "journal-verify-package-play":
            output = {"verified": True, **verify_journal_package_play(
                _required_json(args.play, "play", MAX_TRANSFER_BYTES),
                require_all=args.require_all,
            )}
        elif args.command == "legal-actions":
            output = legal_action_report(_required_json(args.bundle, "bundle"))
        elif args.command == "verify-legal-actions":
            output = {"verified": True, "legal_actions": verify_legal_action_report(
                _required_json(args.report, "report", MAX_GUIDANCE_BYTES))}
        elif args.command == "journal-compare":
            output = compare_journals(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.other_journal, "other-journal", MAX_JOURNAL_BYTES),
            )
        elif args.command == "journal-verify-comparison":
            output = {"verified": True, **verify_journal_comparison(
                _required_json(args.comparison, "comparison", MAX_COMPARISON_BYTES))}
        elif args.command == "journal-fast-forward":
            if not args.expected_journal_digest:
                raise HarborError("--expected-journal-digest is required")
            output = fast_forward_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.other_journal, "other-journal", MAX_JOURNAL_BYTES),
                expected_journal_digest=args.expected_journal_digest,
            )
        elif args.command == "journal-init":
            output = create_journal(_required_json(args.bundle, "bundle"))
        elif args.command == "journal-verify":
            output = {"verified": True, **verify_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES))}
        elif args.command == "journal-export":
            output = journal_head(_required_json(args.journal, "journal", MAX_JOURNAL_BYTES))
        elif args.command == "journal-audit":
            output = journal_audit(_required_json(args.journal, "journal", MAX_JOURNAL_BYTES))
        elif args.command == "journal-at":
            if args.revision_index is None:
                raise HarborError("--revision-index is required for journal-at")
            output = journal_at(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                args.revision_index,
            )
        elif args.command == "journal-rewind":
            if args.revision_index is None or not args.expected_journal_digest:
                raise HarborError("--revision-index and --expected-journal-digest are required")
            output = rewind_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                args.revision_index, expected_journal_digest=args.expected_journal_digest,
            )
        elif args.command == "journal-append":
            if not args.expected_journal_digest:
                raise HarborError("--expected-journal-digest is required")
            output = append_journal(
                _required_json(args.journal, "journal", MAX_JOURNAL_BYTES),
                _required_json(args.actions, "actions"),
                expected_journal_digest=args.expected_journal_digest,
                require_win=args.require_win,
            )
        elif args.command == "verify-npc-forecast":
            output = {"verified": True, "terminal": verify_npc_forecast(
                _required_json(args.report, "report", MAX_NPC_BYTES))}
        elif args.command == "npc-forecast":
            if args.tick is None:
                raise HarborError("--tick is required for npc-forecast")
            output = npc_forecast(_required_json(args.bundle, "bundle"), args.tick)
        elif args.command == "verify-npc-report":
            output = {"verified": True, "terminal": verify_npc_observations(
                _required_json(args.report, "report", MAX_NPC_BYTES))}
        elif args.command == "npc-report":
            output = npc_observations(_required_json(args.bundle, "bundle"))
        elif args.command == "verify-market-distribution-play":
            output = {"verified": True, "totals": verify_market_distribution_play(
                _required_json(args.play, "play", MAX_DISTRIBUTION_BYTES * 2),
                require_all=args.require_all)}
        elif args.command == "market-distribution-play":
            output = play_market_distribution(
                _required_json(args.package, "package", MAX_DISTRIBUTION_BYTES),
                _required_json(args.actions, "actions"), require_all=args.require_all)
        elif args.command == "verify-market-distribution":
            output = {"verified": True, **verify_market_distribution(
                _required_json(args.package, "package", MAX_DISTRIBUTION_BYTES))}
        elif args.command == "market-distribution":
            output = build_market_distribution(
                load_source(Path(args.source)), decode(_read(args.missions)), choice=args.choice)
        elif args.command == "verify-market-balance":
            output = {"verified": True, **verify_market_balance(
                _required_json(args.comparison, "comparison", MAX_BALANCE_BYTES))}
        elif args.command == "market-balance":
            if not args.expected_source_digest:
                raise HarborError("--expected-source-digest is required for market-balance")
            output = balance_market(
                load_source(Path(args.source)), decode(_read(args.missions)),
                _required_json(args.edits, "edits"),
                expected_source_digest=args.expected_source_digest, choice=args.choice)
        elif args.command == "market-apply":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for market-apply")
            output = apply_market_preview(
                _required_json(args.preview, "preview", MAX_PREVIEW_BYTES),
                expected_terminal_digest=args.expected_terminal_digest, require_win=args.require_win)
        elif args.command == "verify-market-preview":
            output = {"verified": True, **verify_market_preview(
                _required_json(args.preview, "preview", MAX_PREVIEW_BYTES))}
        elif args.command == "market-preview":
            output = preview_market(
                _required_json(args.bundle, "bundle"), _required_json(args.actions, "actions"))
        elif args.command == "verify-market-futures":
            output = {"verified": True, "branches": verify_market_futures(
                _required_json(args.report, "report", MAX_MARKET_BYTES * 4))}
        elif args.command == "market-futures":
            output = market_futures(_required_json(args.bundle, "bundle"))
        elif args.command == "market-checkpoint":
            if args.tick is None:
                raise HarborError("--tick is required for market-checkpoint")
            output = market_checkpoint(_required_json(args.report, "report", MAX_MARKET_BYTES), args.tick)
        elif args.command == "market-resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for market-resume")
            output = market_resume(
                _required_json(args.report, "report", MAX_MARKET_BYTES), _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest, require_win=args.require_win)
        elif args.command == "verify-market":
            output = {"verified": True, "totals": verify_market_report(
                _required_json(args.report, "report", MAX_MARKET_BYTES))}
        elif args.command == "market-report":
            output = market_report(_required_json(args.bundle, "bundle"))
        elif args.command == "package-verify-play":
            output = {"verified": True, **verify_package_play(
                _required_json(args.play, "play"), require_all=args.require_all)}
        elif args.command == "package-play":
            output = play_package(
                _required_json(args.package, "package"), _required_json(args.actions, "actions"),
                require_all=args.require_all)
        elif args.command == "package-verify":
            output = {"verified": True, **verify_package(_required_json(args.package, "package"))}
        elif args.command == "package-build":
            output = build_package(
                load_source(Path(args.source)), decode(_read(args.missions)), choice=args.choice)
        elif args.command == "verify-mission-comparison":
            output = {"verified": True, **verify_mission_comparison(
                _required_json(args.comparison, "comparison"))}
        elif args.command == "compare-mission-revision":
            output = compare_mission_revision(
                _required_json(args.mission_revision, "mission-revision"),
                _required_json(args.bundle, "bundle"))
        elif args.command == "verify-mission-portfolio":
            output = {"verified": True, "branches": verify_mission_branch_report(
                _required_json(args.report, "report"))}
        elif args.command == "mission-portfolio":
            output = mission_branch_report(
                _required_json(args.bundle, "bundle"), decode(_read(args.missions)))
        elif args.command == "mission-checkpoint":
            if args.tick is None:
                raise HarborError("--tick is required for mission-checkpoint")
            output = mission_report(
                checkpoint(_required_json(args.bundle, "bundle"), args.tick),
                decode(_read(args.missions)), require_all=args.require_all)
        elif args.command == "mission-resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for mission-resume")
            resumed = resume_bundle(
                _required_json(args.bundle, "bundle"),
                _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest,
            )
            output = mission_report(resumed, decode(_read(args.missions)), require_all=args.require_all)
        elif args.command == "verify-mission-author":
            output = {"verified": True, "board": verify_mission_revision(
                _required_json(args.mission_revision, "mission-revision"))}
        elif args.command == "author-missions":
            if not args.expected_board_digest:
                raise HarborError("--expected-board-digest is required for author-missions")
            output = author_mission_revision(
                decode(_read(args.missions)), load_source(Path(args.source)),
                _required_json(args.mission_edits, "mission-edits"),
                expected_board_digest=args.expected_board_digest,
                preview_bundle=_required_json(args.preview_bundle, "preview-bundle") if args.preview_bundle else None,
            )
        elif args.command == "verify-mission-report":
            result = verify_mission_report(_required_json(args.report, "report"), require_all=args.require_all)
            output = {"verified": True, **result}
        elif args.command == "mission-report":
            output = mission_report(
                _required_json(args.bundle, "bundle"), decode(_read(args.missions)),
                require_all=args.require_all,
            )
        elif args.command == "solve-missions":
            output = solve_missions(
                load_source(Path(args.source)), decode(_read(args.missions)), choice=args.choice,
            )
        elif args.command == "trial-live":
            return play_live(
                load_source(Path(args.source)), sys.stdin, sys.stdout,
                course=_required_json(args.trial, "trial"),
            )
        elif args.command == "play-live":
            return play_live(load_source(Path(args.source)), sys.stdin, sys.stdout)
        elif args.command == "verify-plan":
            state = verify_plan(_required_json(args.plan, "plan"))
            output = {"verified": True, "state": state}
        elif args.command == "solve":
            output = solve(load_source(Path(args.source)), choice=args.choice)
        elif args.command == "verify-author":
            source = verify_revision(_required_json(args.revision, "revision"))
            output = {"verified": True, "source": source}
        elif args.command == "author":
            if not args.expected_source_digest:
                raise HarborError("--expected-source-digest is required for author")
            output = author_revision(
                load_source(Path(args.source)), _required_json(args.edits, "edits"),
                expected_source_digest=args.expected_source_digest,
            )
        elif args.command == "verify":
            state = verify_bundle(_required_json(args.bundle, "bundle"), require_win=args.require_win)
            output = {"verified": True, "state": state}
        elif args.command == "verify-portfolio":
            result = verify_portfolio(_required_json(args.bundle, "bundle"))
            output = {"verified": True, "branches": result}
        elif args.command == "checkpoint":
            if args.tick is None:
                raise HarborError("--tick is required for checkpoint")
            output = checkpoint(_required_json(args.bundle, "bundle"), args.tick)
        elif args.command == "resume":
            if not args.expected_terminal_digest:
                raise HarborError("--expected-terminal-digest is required for resume")
            output = resume_bundle(
                _required_json(args.bundle, "bundle"),
                _required_json(args.actions, "actions"),
                expected_terminal_digest=args.expected_terminal_digest,
                require_win=args.require_win,
            )
        elif args.command == "portfolio":
            output = branch_portfolio(
                _required_json(args.bundle, "bundle"),
                _required_json(args.branches, "branches"),
            )
        else:
            source = load_source(Path(args.source))
            actions = demo_actions() if args.command == "demo" else _required_json(args.actions, "actions")
            output = export_bundle(source, actions, require_win=args.require_win)
        sys.stdout.buffer.write(canonical(output) + b"\n")
        return 0
    except HarborError as exc:
        print("harbor: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
