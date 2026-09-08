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


def test_add_faction_resets_an_existing_faction(dcc_world):
    """add_faction is create-or-reset, matching add_clock/add_track behavior.

    Calling add_faction on an existing name unconditionally wipes members,
    territory, and relations. This makes the contract explicit and guards against
    accidental upsert semantics in refactors.
    """
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_member(TITHE, "Aeron")
    assert m.get_factions()[TITHE]["members"] == ["Aeron"]

    # Calling add_faction on the same name resets it
    m.add_faction(TITHE)
    assert m.get_factions()[TITHE]["members"] == []
    assert m.get_factions()[TITHE]["standing"] == 0


CWM = "Cwm Bedd"


def test_claim_is_idempotent_and_case_insensitive(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.claim(TITHE, CWM)
    m.claim(TITHE, "cwm bedd")
    assert m.get_factions()[TITHE]["territory"] == [CWM]


def test_release_removes_a_claim(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.claim(TITHE, CWM)
    m.release(TITHE, "CWM BEDD")
    assert m.get_factions()[TITHE]["territory"] == []


def test_holders_of_finds_every_claimant(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_faction(WOLVES)
    m.claim(TITHE, CWM)
    m.claim(WOLVES, "cwm bedd")
    assert sorted(m.holders_of(CWM)) == sorted([TITHE, WOLVES])


def test_holders_of_unclaimed_ground_is_empty(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    assert m.holders_of("Preseli") == []
    assert m.holders_of("") == []


def test_contested_lists_only_ground_two_factions_claim(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction(TITHE)
    m.add_faction(WOLVES)
    m.claim(TITHE, CWM)
    m.claim(TITHE, "Preseli")
    m.claim(WOLVES, "cwm bedd")

    contested = m.contested()
    assert list(contested.keys()) == [CWM]
    assert sorted(contested[CWM]) == sorted([TITHE, WOLVES])


def test_claim_on_an_unknown_faction_returns_none(dcc_world):
    assert FactionManager(dcc_world).claim("Nobody", CWM) is None
