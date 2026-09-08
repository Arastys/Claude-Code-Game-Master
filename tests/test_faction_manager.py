"""Tests for faction state.

The bible's `factions` graph is a static, confirm-locked reference. This is the
live half: standing the PC has earned, who belongs to what, and who holds which
ground.
"""

from lib.faction_manager import FactionManager, STANDING_MAX, STANDING_MIN

TITHE = "The Valley Tithe"
WOLVES = "Plant y Lleuad"


def test_add_faction_defaults_to_neutral_standing(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE, note="The families bound to the offering.")
    stored = m.get_factions()[TITHE]
    assert stored["standing"] == 0
    assert stored["members"] == []
    assert stored["territory"] == []
    assert stored["relations"] == {}
    assert stored["note"] == "The families bound to the offering."


def test_standing_clamps_to_the_reaction_roll_range(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    assert m.set_standing(TITHE, 99)["standing"] == STANDING_MAX
    assert m.set_standing(TITHE, -99)["standing"] == STANDING_MIN


def test_adjust_standing_accumulates_and_clamps(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE, standing=3)
    assert m.adjust_standing(TITHE, 1)["standing"] == 4
    assert m.adjust_standing(TITHE, 10)["standing"] == STANDING_MAX
    assert m.adjust_standing(TITHE, -20)["standing"] == STANDING_MIN


def test_membership_is_added_once_and_removed_case_insensitively(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_member(TITHE, "Nest")
    m.add_member(TITHE, "nest")
    assert m.get_factions()[TITHE]["members"] == ["Nest"]

    m.remove_member(TITHE, "NEST")
    assert m.get_factions()[TITHE]["members"] == []


def test_membership_persists_between_managers(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_member(TITHE, "Aeron")
    assert FactionManager(dcc_world).get_factions()[TITHE]["members"] == ["Aeron"]


def test_operations_on_an_unknown_faction_return_none(dcc_world):
    m = FactionManager(dcc_world)
    assert m.set_standing(WOLVES, 1) is None
    assert m.adjust_standing(WOLVES, 1) is None
    assert m.add_member(WOLVES, "Nest") is None


def test_remove_faction(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    assert m.remove_faction(TITHE) is True
    assert m.remove_faction(TITHE) is False
