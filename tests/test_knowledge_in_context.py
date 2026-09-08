"""The WHO KNOWS WHAT block — the discipline half of the ledger.

The point is the negative space: the block must show me what a present NPC does
NOT know, so I never have them react to something nobody told them. It must also
stay silent in a world that never uses it.
"""

import json

import pytest

from lib.knowledge_manager import KnowledgeManager
from lib.session_manager import SessionManager
from tests.test_kit_vitals import _make_world

MILESTONE_RULESET = {
    "name": "custom",
    "stat_schema": {"attributes": ["might", "cunning"], "vitals": ["hp"]},
    "progression": {"model": "milestone"},
}
DND5E_RULESET = {
    "name": "dnd5e",
    "stat_schema": {
        "attributes": ["str", "dex", "con", "int", "wis", "cha"],
        "vitals": ["hp"],
    },
    "progression": {"model": "xp-levels"},
}
RESOURCE_AXIS_RULESET = {
    "name": "dcc",
    "stat_schema": {"attributes": ["str", "agi"], "vitals": ["hp"]},
    "progression": {"model": "resource-axis", "axis": "viewers"},
}

DROWNED = "the child drowned in Nant Ddu"
AGELESS = "Rhiannon does not age"


def _world_with_npcs(tmp_path, slug, ruleset, npcs, location="Cwm Bychan"):
    world = _make_world(tmp_path, slug, ruleset)
    campaign = world / "campaigns" / slug
    (campaign / "npcs.json").write_text(json.dumps(npcs), encoding="utf-8")
    (campaign / "campaign-overview.json").write_text(
        json.dumps({"player_position": {"current_location": location}}),
        encoding="utf-8")
    return world


def _npc(location="Cwm Bychan"):
    return {"description": "a villager", "attitude": "neutral",
            "tags": {"locations": [location]}}


# --- The pure renderer ---

def test_render_is_empty_when_nothing_is_relevant(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Someone Far Away", "knows")
    assert KnowledgeManager.render(m.get_propositions(), ["Mair"]) == ""


def test_render_shows_a_present_npc_who_does_not_know(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, truth="true")
    m.set_stance("P1", "Mair", "knows", source="told by Eurgain", session=5)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair", "Gwen"])
    assert "P1" in out
    assert AGELESS in out
    assert "(true)" in out
    assert "KNOWS" in out
    assert "s5, told by Eurgain" in out
    assert "Gwen" in out and "unaware" in out


def test_a_false_proposition_is_marked_loudly(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED, truth="false")
    m.set_stance("P1", "Mair", "knows", session=2)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "(FALSE)" in out


def test_a_proposition_about_a_present_npc_shows_even_when_nobody_present_holds_it(dcc_world):
    """Dramatic irony: the thing is about her and she has not been told."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "P1" in out
    assert "unaware" in out


def test_an_absent_stance_holder_still_appears_under_the_proposition(dcc_world):
    """A faction is how the leak becomes visible; it is never 'present'."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "Y Bleiddiaid" in out


def test_a_faction_that_knows_names_the_member_who_does_not(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    factions = {"Y Bleiddiaid": {"members": ["Mair", "Gwen"]}}
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"], factions=factions)
    assert "— Mair does not" in out


def test_two_members_who_do_not_know_are_named_together(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    factions = {"Y Bleiddiaid": {"members": ["Mair", "Gwen"]}}
    out = KnowledgeManager.render(m.get_propositions(), ["Mair", "Gwen"],
                                  factions=factions)
    assert "— Mair, Gwen do not" in out


def test_a_member_who_already_knows_is_not_named(dcc_world):
    # NOTE: uses DROWNED rather than the brief's AGELESS here. AGELESS is the
    # literal statement "Rhiannon does not age", whose text is always rendered
    # verbatim in the proposition line — so `assert "does not" not in out`
    # could never pass regardless of implementation correctness, since the
    # substring "does not" is baked into the statement itself. DROWNED carries
    # no such collision and the test's actual intent (a member who already
    # knows is never named in the "— X does not" annotation) is unaffected.
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED, about="Mair")
    m.set_stance("P1", "Y Bleiddiaid", "knows", session=1)
    m.set_stance("P1", "Mair", "knows", session=2)
    factions = {"Y Bleiddiaid": {"members": ["Mair"]}}
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"], factions=factions)
    assert "does not" not in out


def test_dormant_propositions_are_counted_not_shown(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    m.add_proposition(DROWNED, status="dormant")
    m.add_proposition("a third", status="dormant")
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert DROWNED not in out
    assert "2 dormant propositions not shown." in out


def test_one_dormant_proposition_is_singular(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    m.add_proposition(DROWNED, status="dormant")
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "1 dormant proposition not shown." in out


def test_only_the_five_most_recently_touched_are_shown(dcc_world):
    m = KnowledgeManager(dcc_world)
    for i in range(7):
        m.add_proposition(f"thing {i}")
        m.set_stance(f"P{i + 1}", "Mair", "knows", session=i)
    out = KnowledgeManager.render(m.get_propositions(), ["Mair"])
    assert "thing 6" in out and "thing 2" in out
    assert "thing 1" not in out and "thing 0" not in out


def test_relevant_reports_the_shown_set_and_the_dormant_count(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    m.add_proposition(DROWNED, status="dormant")
    shown, dormant = KnowledgeManager.relevant(m.get_propositions(), ["Mair"])
    assert [pid for pid, _ in shown] == ["P1"]
    assert dormant == 1


# --- In the scene brief, across three kits ---

@pytest.mark.parametrize("slug,ruleset", [
    ("custom-kit", MILESTONE_RULESET),
    ("forgotten-realms", DND5E_RULESET),
    ("dcc-axis", RESOURCE_AXIS_RULESET),
])
def test_an_empty_ledger_leaves_the_brief_completely_silent(tmp_path, slug, ruleset):
    world = _world_with_npcs(tmp_path, slug, ruleset, {"Mair": _npc()})
    ctx = SessionManager(world).get_full_context()
    assert "WHO KNOWS WHAT" not in ctx


@pytest.mark.parametrize("slug,ruleset", [
    ("custom-kit", MILESTONE_RULESET),
    ("forgotten-realms", DND5E_RULESET),
    ("dcc-axis", RESOURCE_AXIS_RULESET),
])
def test_the_block_appears_for_every_kit_when_the_ledger_is_used(tmp_path, slug, ruleset):
    world = _world_with_npcs(tmp_path, slug, ruleset,
                             {"Mair": _npc(), "Gwen": _npc()})
    m = KnowledgeManager(world)
    m.add_proposition(AGELESS, truth="true")
    m.set_stance("P1", "Mair", "knows", source="told by Eurgain", session=5)
    ctx = SessionManager(world).get_full_context()
    assert "--- WHO KNOWS WHAT (present) ---" in ctx
    assert AGELESS in ctx
    assert "Gwen" in ctx


def test_a_ledger_with_nothing_relevant_to_this_room_stays_silent(tmp_path):
    """An active proposition about people who are elsewhere must not fill the brief."""
    world = _world_with_npcs(tmp_path, "custom-kit", MILESTONE_RULESET,
                             {"Mair": _npc()})
    m = KnowledgeManager(world)
    m.add_proposition("something in another valley")
    m.set_stance("P1", "A Stranger", "knows")
    assert "WHO KNOWS WHAT" not in SessionManager(world).get_full_context()


def test_the_block_sits_before_pending_consequences(tmp_path):
    world = _world_with_npcs(tmp_path, "custom-kit", MILESTONE_RULESET,
                             {"Mair": _npc()})
    m = KnowledgeManager(world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    ctx = SessionManager(world).get_full_context()
    assert ctx.index("WHO KNOWS WHAT") < ctx.index("PENDING CONSEQUENCES")


def test_ties_on_touched_order_numerically_not_lexicographically(dcc_world):
    """P9 must sort before P10.

    Every proposition written in one session shares a `touched` value, so ties are
    the normal case rather than an edge case. A raw string sort renders
    P10 P11 P6 P7 P8 and silently drops P9 at the five-proposition cap.
    """
    props = {f"P{i}": {"statement": f"thing {i}", "truth": "true",
                       "status": "active", "touched": 3,
                       "stances": {"Mair": {"stance": "knows", "since": 3}}}
             for i in range(6, 12)}
    shown, _ = KnowledgeManager.relevant(props, ["Mair"])
    assert [pid for pid, _ in shown] == ["P6", "P7", "P8", "P9", "P10"]
