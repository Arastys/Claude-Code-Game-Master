"""Tests for campaign-overview-author: seed overview + campaign_rules, fix rules_doc."""

import json
from lib.overview_seed import seed_overview, fix_rules_doc


def test_seed_sets_fields_and_campaign_rules_preserving_others(tmp_path):
    (tmp_path / "campaign-overview.json").write_text(json.dumps({
        "campaign_name": "scaffold", "genre": "Fantasy",
        "player_position": {"current_location": "X"}, "session_count": 3,
    }))
    seed_overview(
        str(tmp_path),
        fields={"campaign_name": "The Iron Tangle", "genre": "LitRPG / Comedy-Horror"},
        campaign_rules={"loot_boxes": "open at saferooms"},
    )
    o = json.loads((tmp_path / "campaign-overview.json").read_text(encoding="utf-8"))
    assert o["campaign_name"] == "The Iron Tangle"
    assert o["genre"] == "LitRPG / Comedy-Horror"
    assert o["campaign_rules"]["loot_boxes"] == "open at saferooms"
    # untouched fields preserved
    assert o["session_count"] == 3
    assert o["player_position"] == {"current_location": "X"}


def test_fix_rules_doc_nulls_dangling_pointer(tmp_path):
    (tmp_path / "ruleset.json").write_text(json.dumps({"name": "K", "rules_doc": "rules.md"}))
    # rules.md does NOT exist
    r = fix_rules_doc(str(tmp_path))
    assert r["changed"] is True
    assert r["rules_doc"] is None
    assert json.loads((tmp_path / "ruleset.json").read_text(encoding="utf-8"))["rules_doc"] is None


def test_fix_rules_doc_leaves_valid_pointer(tmp_path):
    (tmp_path / "rules.md").write_text("# rules")
    (tmp_path / "ruleset.json").write_text(json.dumps({"name": "K", "rules_doc": "rules.md"}))
    r = fix_rules_doc(str(tmp_path))
    assert r["changed"] is False
    assert r["rules_doc"] == "rules.md"


def test_campaign_rules_readable_by_worldkit_shape(tmp_path):
    # WorldKit.campaign_rules() does overview.get("campaign_rules", {}) — ensure shape.
    seed_overview(str(tmp_path), fields={"campaign_name": "T"}, campaign_rules={"viewers": "currency"})
    o = json.loads((tmp_path / "campaign-overview.json").read_text(encoding="utf-8"))
    assert o.get("campaign_rules", {}).get("viewers") == "currency"
