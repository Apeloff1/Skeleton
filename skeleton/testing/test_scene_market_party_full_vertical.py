"""Full cooperative production vertical: play, author, save, rank, compare, export."""
from __future__ import annotations

import json

from skeleton.game.gameplay.scene_market_party import (
    original_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_balance import (
    analyze_party_balance, verify_party_balance,
)
from skeleton.game.gameplay.scene_market_party_compare import (
    compare_party, select_party, verify_selection,
)
from skeleton.game.gameplay.scene_market_party_league import (
    new_league, record_attempt,
)
from skeleton.game.gameplay.scene_market_party_league_author import (
    edit_league, preview_league, verify_league_edit,
)
from skeleton.game.gameplay.scene_market_party_portfolio import (
    import_portfolio, pack_portfolio,
)
from skeleton.game.gameplay.scene_market_party_vault import (
    import_vault, export_vault, new_vault, read_slot, transact_vault,
)


def test_original_source_to_play_to_author_to_save_to_rank_to_export():
    source, turns = original_party()
    played = simulate_party(source, turns)
    partial = simulate_party(source, turns[:len(turns) // 2])
    empty = new_league(source)
    edit = edit_league(empty, {"credits": 4},
                       expected_state_digest=empty["state_digest"])
    assert verify_league_edit(empty, edit) == edit
    preview = preview_league(edit["league"], played)
    assert preview["ranking"]["ranking"][0]["party_state_digest"] == played["state_digest"]
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": played})
    restored = import_vault(json.loads(json.dumps(export_vault(vault))))
    assert read_slot(restored, "campaign") == played
    league = record_attempt(edit["league"], "original", played, expected_revision=0)
    report = compare_party(played, partial)
    assert report["common_prefix_turns"] == len(partial["journal"])
    selection = select_party(played, partial, "left",
                             expected_left_digest=played["state_digest"],
                             expected_right_digest=partial["state_digest"])
    assert verify_selection(played, partial, selection) == selection
    balance = analyze_party_balance(played)
    assert verify_party_balance(played, balance) == balance
    portfolio = pack_portfolio(played, restored, league, slot="campaign")
    assert import_portfolio(json.loads(json.dumps(portfolio))) == portfolio
    assert portfolio["ranking"]["ranking"][0]["party_state_digest"] == played["state_digest"]
    assert balance["turns"] == len(turns)
