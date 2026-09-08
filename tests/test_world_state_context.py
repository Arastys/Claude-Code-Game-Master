"""World tracks and factions must reach the GM through scene context.

State the GM never sees is state that does not exist at the table.
"""

from lib.faction_manager import FactionManager
from lib.session_manager import SessionManager
from lib.world_tracks import WorldTrackManager


def test_world_tracks_render_into_context(dcc_world):
    WorldTrackManager(dcc_world).add_track(
        "Y Cof", 6, current=2, note="What the world remembers.")
    context = SessionManager(dcc_world).get_full_context()
    assert "--- WORLD TRACKS ---" in context
    assert "Y Cof" in context
    assert "2/6" in context


def test_factions_render_into_context(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction("The Valley Tithe", standing=2)
    m.claim("The Valley Tithe", "Cwm Bedd")
    context = SessionManager(dcc_world).get_full_context()
    assert "--- FACTIONS ---" in context
    assert "The Valley Tithe" in context
    assert "Cwm Bedd" in context


def test_contested_ground_is_flagged(dcc_world):
    m = FactionManager(dcc_world)
    m.add_faction("The Valley Tithe")
    m.add_faction("Plant y Lleuad")
    m.claim("The Valley Tithe", "Cwm Bedd")
    m.claim("Plant y Lleuad", "Cwm Bedd")
    context = SessionManager(dcc_world).get_full_context()
    assert "CONTESTED" in context
    assert "Cwm Bedd" in context


def test_sections_are_absent_when_nothing_is_declared(dcc_world):
    context = SessionManager(dcc_world).get_full_context()
    assert "--- WORLD TRACKS ---" not in context
    assert "--- FACTIONS ---" not in context
