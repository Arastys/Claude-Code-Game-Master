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


from lib.consequence_manager import ConsequenceManager

RUMOUR = "A rumour with the right shape is circulating."


def _active(world):
    data = ConsequenceManager(world).json_ops.load_json("consequences.json") or {}
    return [c.get("consequence", "") for c in data.get("active", [])]


def _fired(world, needle=RUMOUR):
    return [c for c in _active(world) if needle in c]


def test_climbing_past_a_threshold_fires_its_consequence(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.adjust("Y Cof", 3)
    fired = _fired(dcc_world)
    assert len(fired) == 1
    assert "[Track — Y Cof]" in fired[0]
    assert len(result["fired"]) == 1


def test_falling_past_a_threshold_fires_nothing(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS, current=6)
    result = m.adjust("Y Cof", -4)
    assert _fired(dcc_world) == []
    assert result["fired"] == []


def test_climbing_two_thresholds_at_once_fires_both(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    result = m.adjust("Y Cof", 5)
    assert len(result["fired"]) == 2


def test_threshold_without_a_consequence_fires_nothing(dcc_world):
    m = WorldTrackManager(dcc_world)
    m.add_track("Quiet", 3, thresholds=[{"at": 1}])
    before = len(_active(dcc_world))
    result = m.adjust("Quiet", 1)
    assert result["fired"] == []
    assert len(_active(dcc_world)) == before


def test_firing_keeps_stdout_parseable(dcc_world, capsys):
    """adjust() is behind a --json CLI path; a fire must not leak onto stdout."""
    m = WorldTrackManager(dcc_world)
    m.add_track("Y Cof", 6, thresholds=THRESHOLDS)
    capsys.readouterr()
    m.adjust("Y Cof", 3)
    out = capsys.readouterr()
    assert out.out.strip() == "", f"fire leaked onto stdout: {out.out!r}"


import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(world, *args):
    env = dict(os.environ, GM_WORLD_STATE_BASE=str(world))
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "lib" / "world_tracks.py"), *args],
        capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))


def test_cli_list_emits_a_json_envelope(dcc_world):
    WorldTrackManager(dcc_world).add_track("Y Cof", 6, thresholds=THRESHOLDS)
    proc = _run_cli(dcc_world, "list", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["Y Cof"]["max"] == 6


def test_cli_adjust_json_stays_parseable_when_a_threshold_fires(dcc_world):
    WorldTrackManager(dcc_world).add_track("Y Cof", 6, thresholds=THRESHOLDS)
    proc = _run_cli(dcc_world, "adjust", "Y Cof", "--delta", "3", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["data"]["after"] == 3
    assert len(payload["data"]["fired"]) == 1


def test_cli_adjust_unknown_track_emits_error_envelope(dcc_world):
    proc = _run_cli(dcc_world, "adjust", "Nothing", "--delta", "1", "--json")
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "no such track" in payload["error"]


def test_cli_add_malformed_thresholds_json_emits_error_envelope(dcc_world):
    proc = _run_cli(dcc_world, "add", "X", "5", "--thresholds-json", "{not valid json", "--json")
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "--thresholds-json" in payload["error"]


# --- Wrapper-level test (additional requirement, beyond the brief) ---
#
# The two CLI tests above invoke lib/world_tracks.py directly via
# sys.executable, which never touches tools/gm-track.sh. That is not enough:
# a wrapper that turned out to be a `case` dispatcher rather than a genuine
# `"$@"` pass-through to the Python manager would print a usage banner and
# exit 0 while these tests kept passing. Drive the real bash wrapper as a
# subprocess so a mis-wired wrapper is actually caught — json.loads() below
# fails hard on a usage banner instead of silently accepting it.


def _run_wrapper(dcc_world, *args):
    return subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "gm-track.sh"), *args],
        capture_output=True, text=True,
        env={**os.environ, "GM_WORLD_STATE_BASE": str(dcc_world)},
        cwd=str(REPO_ROOT))


def test_wrapper_list_reaches_the_python_manager(dcc_world):
    WorldTrackManager(dcc_world).add_track("Y Cof", 6, thresholds=THRESHOLDS)
    proc = _run_wrapper(dcc_world, "list", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["Y Cof"]["max"] == 6


def test_wrapper_adjust_reaches_the_python_manager_and_fires_a_consequence(dcc_world):
    WorldTrackManager(dcc_world).add_track("Y Cof", 6, thresholds=THRESHOLDS)
    proc = _run_wrapper(dcc_world, "adjust", "Y Cof", "--delta", "3", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["data"]["after"] == 3
    assert len(payload["data"]["fired"]) == 1
