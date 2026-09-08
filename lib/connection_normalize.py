#!/usr/bin/env python3
"""Normalize location connection targets to real keys; relocate rule-phrases.

Connection `to` values are a mix of real locations with drift ("Station 435 (end of
line)" vs the key "...(End of the Line)") and pattern/rule statements that are not
places at all ("Any line", "Transfer stations ending in 1", "Upper level via central
stairs"). This canonicalizes resolvable targets via the alias resolver and moves
rule-phrases into the location's `notes` (so they are not silently dropped by
reconcile). Genuinely-missing place names are left for missing-location-reconcile.

Run after cap, before reconcile.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from entity_aliases import resolve_entity_name

# Phrases that describe a routing RULE, not a destination location.
_RULE_MARKERS = (
    "ending in", "stations ending", "any line", "any station", "any train",
    " via ", "upper level", "lower level", "central stair", "all lines",
    "any of", "every station",
)


def _is_rule_phrase(to: str) -> bool:
    low = (to or "").lower()
    return any(m in low for m in _RULE_MARKERS)


def coerce_connections(locations: dict) -> int:
    """Coerce bare-string connection entries to {"to": <string>} dicts in place.

    Extractor agents sometimes emit `connections` as a list of plain location
    names instead of the runtime {to, path} dict shape. The whole runtime
    (move, integrity, location_manager) indexes `conn["to"]`, so a bare string
    crashes with AttributeError. Coerce here so every downstream step operates
    on dicts. Already-dict entries are left untouched; non-str/non-dict junk is
    dropped. Returns the number of string entries coerced.
    """
    coerced = 0
    for loc in (locations or {}).values():
        if not isinstance(loc, dict):
            continue
        conns = loc.get("connections")
        if conns is None:
            continue
        if not isinstance(conns, list):
            loc["connections"] = []
            continue
        fixed = []
        for conn in conns:
            if isinstance(conn, dict):
                fixed.append(conn)
            elif isinstance(conn, str) and conn.strip():
                fixed.append({"to": conn.strip()})
                coerced += 1
            # else: neither dict nor usable string -> drop
        loc["connections"] = fixed
    return coerced


def normalize_connections(locations: dict) -> dict:
    """Canonicalize/relocate connection targets in place. Returns a report."""
    report = {"canonicalized": [], "relocated": [], "left": []}
    coerce_connections(locations)
    for lname, loc in (locations or {}).items():
        if not isinstance(loc, dict):
            continue
        kept = []
        for conn in loc.get("connections", []) or []:
            if not (isinstance(conn, dict) and "to" in conn):
                kept.append(conn)
                continue
            to = conn["to"]
            key = resolve_entity_name(to, locations)
            if key:
                if key != to:
                    report["canonicalized"].append({"loc": lname, "from": to, "to": key})
                conn["to"] = key
                kept.append(conn)
            elif _is_rule_phrase(to):
                path = conn.get("path", "")
                note = f"Connection rule: {to}" + (f" ({path})" if path else "")
                notes = loc.get("notes")
                if isinstance(notes, list):
                    notes.append(note)
                else:
                    loc["notes"] = ((notes + " ") if notes else "") + note
                report["relocated"].append({"loc": lname, "rule": to})
                # dropped from connections (now a note)
            else:
                kept.append(conn)  # genuinely missing place -> leave for reconcile
                report["left"].append({"loc": lname, "to": to})
        loc["connections"] = kept
    return report


def run_normalize(campaign_dir) -> dict:
    path = Path(campaign_dir) / "locations.json"
    locations = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report = normalize_connections(locations)
    if locations:
        path.write_text(json.dumps(locations, indent=2))
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Normalize connection targets")
    parser.add_argument("campaign_dir")
    args = parser.parse_args()
    r = run_normalize(args.campaign_dir)
    print(f"  canonicalized: {len(r['canonicalized'])}")
    print(f"  relocated to notes: {len(r['relocated'])}")
    print(f"  left for reconcile: {len(r['left'])}")


if __name__ == "__main__":
    main()
