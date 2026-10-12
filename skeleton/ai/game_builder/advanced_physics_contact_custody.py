"""Canonical, finite contact-to-original-geometry ledger.

This helper has no dependency on physics engine modules: AABB contacts,
discrete oriented SAT and temporal rotating SAT all write the same signed
source fixture index while retaining distinct contact kinds. Counts survive
the entire replay; detailed evidence retains a bounded 96-event window.
"""


def record_fixture_contact(state,body,index,kind):
    if (type(index) is not int or not 0<=index<len(state["fixtures"]) or
        len(state["fixture_contact_counts"])!=len(state["fixtures"]) or
        type(kind) is not str or kind not in (
            "swept_fixture_contact","fixture_contact",
            "oriented_fixture","rotating_swept_fixture",
        )):
        raise ValueError("unregistered authored physics fixture contact identity")
    state["fixture_contact_counts"][index]+=1
    history=state["fixture_contact_events"]
    if len(history)>=96:
        history.pop(0)
    history.append({
        "fixture_index":index,"body_id":body["id"],"kind":kind,
        "tick":state["tick"],"frame":state["frame"],
        "position":list(body["position"]),
    })


__all__=["record_fixture_contact"]
