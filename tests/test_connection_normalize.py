"""Tests for connection-key-normalize."""

import json
from lib.connection_normalize import normalize_connections, _is_rule_phrase, run_normalize


def test_rule_phrase_detection_precise():
    assert _is_rule_phrase("Transfer stations ending in 1")
    assert _is_rule_phrase("Upper level via central stairs")
    assert _is_rule_phrase("Any line")
    # a real place must NOT be flagged as a rule
    assert not _is_rule_phrase("Transfer Station 89")
    assert not _is_rule_phrase("Sirin Station 81")


def test_canonicalizes_drifted_target():
    locations = {
        "Station 435 (End of the Line)": {"connections": []},
        "Hub": {"connections": [{"to": "station 435 (end of line)"}]},
    }
    report = normalize_connections(locations)
    assert locations["Hub"]["connections"][0]["to"] == "Station 435 (End of the Line)"
    assert any(c["to"] == "Station 435 (End of the Line)" for c in report["canonicalized"])


def test_rule_phrase_moved_to_notes_and_removed():
    locations = {"Hub": {"connections": [{"to": "Transfer stations ending in 1", "path": "any time"}], "notes": ""}}
    normalize_connections(locations)
    assert locations["Hub"]["connections"] == []
    assert "Connection rule: Transfer stations ending in 1" in locations["Hub"]["notes"]


def test_missing_real_place_left_for_reconcile():
    locations = {"Hub": {"connections": [{"to": "Transfer Station 89"}]}}
    report = normalize_connections(locations)
    # not a rule, not a key -> kept for reconcile
    assert locations["Hub"]["connections"][0]["to"] == "Transfer Station 89"
    assert report["left"] and report["left"][0]["to"] == "Transfer Station 89"


def test_run_normalize_writes(tmp_path):
    (tmp_path / "locations.json").write_text(json.dumps({
        "A": {"connections": [{"to": "Any line"}]},
    }))
    run_normalize(str(tmp_path))
    saved = json.loads((tmp_path / "locations.json").read_text(encoding="utf-8"))
    assert saved["A"]["connections"] == []
    assert "Any line" in saved["A"]["notes"]
