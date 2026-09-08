"""Tests for world tracks.

A threat clock only fills. A world track moves both ways and reports the
thresholds it crosses in either direction, because the world forgetting
something is as much a beat as the world learning it.
"""

from lib.world_tracks import WorldTrackManager

THRESHOLDS = [
    {"at": 3, "consequence": "A rumour with the right shape is circulating."},
    {"at": 5, "consequence": "The valley knows how to finish one of the Old Dead."},
]


def test_add_track_stores_shape_and_starts_empty(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS, note="What the world remembers.")
    stored = m.get_tracks()["Y Cof"]
    assert stored["current"] == 0
    assert stored["max"] == 6
    assert stored["thresholds"] == THRESHOLDS
    assert stored["note"] == "What the world remembers."


def test_adjust_clamps_to_zero_and_max(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6)
    assert m.adjust("Y Cof", 99)["after"] == 6
    assert m.adjust("Y Cof", -99)["after"] == 0


def test_adjust_reports_thresholds_crossed_climbing(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.adjust("Y Cof", 5)
    assert [t["at"] for t in result["crossed"]] == [3, 5]
    assert result["before"] == 0
    assert result["after"] == 5


def test_adjust_reports_thresholds_crossed_falling(dcc_world):
    """The forgetting direction is a beat too — this is why it is not a clock."""
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS, current=6)
    result = m.adjust("Y Cof", -4)
    assert [t["at"] for t in result["crossed"]] == [3, 5]
    assert result["after"] == 2


def test_adjust_persists_between_managers(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6)
    m.adjust("Y Cof", 4)
    assert WorldTrackManager(dcc_world).get_tracks()["Y Cof"]["current"] == 4


def test_set_value_reports_crossings(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.set_value("Y Cof", 4)
    assert result["after"] == 4
    assert [t["at"] for t in result["crossed"]] == [3]


def test_adjust_unknown_track_returns_none(dcc_world):
    assert WorldTrackManager(dcc_world).adjust("Nothing", 1) is None


def test_remove_track(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6)
    assert m.remove_track("Y Cof") is True
    assert m.remove_track("Y Cof") is False
    assert "Y Cof" not in m.get_tracks()


def test_render_shows_a_bar_and_value(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, current=2)
    out = WorldTrackManager.render(m.get_tracks())
    assert "Y Cof" in out
    assert "2/6" in out


def test_add_track_clamps_high_initial_value(dcc_world):
    """Creation-time clamping: initial value above max is clamped to max."""
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, current=99)
    assert m.get_tracks()["Y Cof"]["current"] == 6


def test_add_track_clamps_negative_initial_value(dcc_world):
    """Creation-time clamping: negative initial value is clamped to 0."""
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, current=-5)
    assert m.get_tracks()["Y Cof"]["current"] == 0
