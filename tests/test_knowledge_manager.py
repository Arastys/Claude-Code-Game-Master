"""Tests for the knowledge ledger.

facts.json holds world truth. This holds the contested half: who has actually
been told what, and who is confidently wrong.
"""

import pytest

from lib.knowledge_manager import (
    KnowledgeManager, TRUTHS, STANCES, STATUSES, UNAWARE,
)

DROWNED = "the child drowned in Nant Ddu"
AGELESS = "Rhiannon does not age"


def test_vocabulary_is_pinned_to_the_literals():
    """Pin the literals, not the constants against themselves. Adding a fourth
    stance would keep `assert x in STANCES` green while breaking every consumer
    that renders or branches on the three."""
    assert TRUTHS == ("true", "false", "unresolved")
    assert STANCES == ("knows", "suspects")
    assert STATUSES == ("active", "dormant")
    assert UNAWARE == "unaware"


def test_add_proposition_assigns_an_id_and_defaults(dcc_world):
    m = KnowledgeManager(dcc_world)
    entry = m.add_proposition(DROWNED)
    assert entry["id"] == "P1"
    assert entry["statement"] == DROWNED
    assert entry["truth"] == "unresolved"
    assert entry["status"] == "active"
    assert entry["stances"] == {}
    assert "about" not in entry


def test_ids_are_monotonic_and_never_reused(dcc_world):
    m = KnowledgeManager(dcc_world)
    assert m.add_proposition(DROWNED)["id"] == "P1"
    assert m.add_proposition(AGELESS)["id"] == "P2"
    # Going dormant is retirement; the counter does not rewind.
    m.set_status("P2", "dormant")
    assert m.add_proposition("a third thing")["id"] == "P3"


def test_a_false_proposition_is_how_a_lie_is_stored(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED, truth="false", session=2)
    m.set_stance("P1", "Mair", "knows", source="told by Rhiannon", session=2)
    entry = m.get_propositions()["P1"]
    assert entry["truth"] == "false"
    assert entry["stances"]["Mair"]["stance"] == "knows"
    assert entry["stances"]["Mair"]["source"] == "told by Rhiannon"
    assert entry["stances"]["Mair"]["since"] == 2


def test_absence_is_unaware_and_is_never_stored(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    assert m.stance_of("P1", "Gwen") == UNAWARE
    assert m.get_propositions()["P1"]["stances"] == {}


def test_forget_returns_a_knower_to_unaware_and_removes_the_record(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "knows")
    assert m.stance_of("P1", "Mair") == "knows"
    m.forget("P1", "MAIR")  # case-insensitive, matching npcs_present
    assert m.stance_of("P1", "Mair") == UNAWARE
    assert m.get_propositions()["P1"]["stances"] == {}


def test_setting_a_stance_stamps_touched_and_since(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS, session=1)
    assert m.get_propositions()["P1"]["touched"] == 1
    m.set_stance("P1", "Mair", "suspects", session=6)
    entry = m.get_propositions()["P1"]
    assert entry["touched"] == 6
    assert entry["stances"]["Mair"]["since"] == 6


def test_a_second_stance_replaces_the_first(dcc_world):
    """Suspicion hardening into certainty is one record changing, not two."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Mair", "suspects", session=3)
    m.set_stance("P1", "Mair", "knows", source="Eurgain told her", session=5)
    stances = m.get_propositions()["P1"]["stances"]
    assert list(stances) == ["Mair"]
    assert stances["Mair"] == {"stance": "knows", "since": 5,
                               "source": "Eurgain told her"}


def test_a_faction_holds_a_stance_of_its_own(dcc_world):
    """No inheritance: the faction knowing says nothing about the member."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    m.set_stance("P1", "Y Bleiddiaid", "knows")
    assert m.stance_of("P1", "Y Bleiddiaid") == "knows"
    assert m.stance_of("P1", "Mair") == UNAWARE


def test_who_knows_resolves_by_id(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    assert list(m.who_knows("P2")) == ["P2"]


def test_who_knows_resolves_by_case_insensitive_substring(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    assert list(m.who_knows("NANT DDU")) == ["P1"]


def test_an_ambiguous_substring_returns_every_match_rather_than_guessing(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition("the ford is watched")
    m.add_proposition("the ford is safe after dark")
    assert sorted(m.who_knows("the ford")) == ["P1", "P2"]


def test_who_knows_prefers_an_exact_id_over_a_statement_substring(dcc_world):
    """A statement that literally contains another proposition's id must not
    hijack a lookup by that id."""
    m = KnowledgeManager(dcc_world)
    m.add_proposition("the marker stone reads P2")
    m.add_proposition(AGELESS)
    assert list(m.who_knows("P2")) == ["P2"]


def test_held_by_reports_every_proposition_one_entity_holds(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(DROWNED)
    m.add_proposition(AGELESS)
    m.add_proposition("the ford is watched")
    m.set_stance("P1", "Mair", "knows")
    m.set_stance("P3", "Mair", "suspects")
    held = m.held_by("Mair")
    assert sorted(held) == ["P1", "P3"]
    assert held["P1"]["stance"] == "knows"
    assert held["P3"]["stance"] == "suspects"


def test_held_by_an_entity_with_no_stances_is_empty(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    assert m.held_by("Gwen") == {}


def test_status_moves_between_active_and_dormant(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    assert m.set_status("P1", "dormant")["status"] == "dormant"
    assert m.set_status("P1", "active")["status"] == "active"


def test_operations_on_an_unknown_proposition_return_none(dcc_world):
    m = KnowledgeManager(dcc_world)
    assert m.set_stance("P99", "Mair", "knows") is None
    assert m.forget("P99", "Mair") is None
    assert m.set_status("P99", "dormant") is None
    assert m.stance_of("P99", "Mair") == UNAWARE


@pytest.mark.parametrize("bad", ["maybe", "TRUE-ish", ""])
def test_an_invalid_truth_value_is_refused(dcc_world, bad):
    with pytest.raises(ValueError):
        KnowledgeManager(dcc_world).add_proposition(AGELESS, truth=bad)


def test_an_invalid_stance_is_refused(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    with pytest.raises(ValueError):
        m.set_stance("P1", "Mair", "certain")


def test_an_invalid_status_is_refused(dcc_world):
    m = KnowledgeManager(dcc_world)
    m.add_proposition(AGELESS)
    with pytest.raises(ValueError):
        m.set_status("P1", "retired")


def test_about_is_stored_only_when_given(dcc_world):
    m = KnowledgeManager(dcc_world)
    entry = m.add_proposition(AGELESS, about="Rhiannon")
    assert entry["about"] == "Rhiannon"
    assert "about" not in m.add_proposition(DROWNED)


def test_the_ledger_survives_a_reload(dcc_world):
    """Every method reloads from disk; nothing is cached in the instance."""
    KnowledgeManager(dcc_world).add_proposition(AGELESS, about="Rhiannon")
    KnowledgeManager(dcc_world).set_stance("P1", "Mair", "knows", session=4)
    fresh = KnowledgeManager(dcc_world).get_propositions()
    assert fresh["P1"]["about"] == "Rhiannon"
    assert fresh["P1"]["stances"]["Mair"]["since"] == 4
