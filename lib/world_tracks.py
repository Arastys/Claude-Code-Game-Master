#!/usr/bin/env python3
"""
World tracks — persisted, world-level named meters.

A threat clock only fills (`ThreatClockManager.advance` clamps the top and not the
bottom, deliberately). A world track moves BOTH ways and reports every threshold it
crosses in either direction, because the world forgetting something over generations
is as much a beat as the world learning it.

Values live in world-tracks.json. All arithmetic delegates to game_core.named_track,
so a stored track behaves exactly like the kit primitive a ruleset declares — the
declaration in ruleset.json `systems` says what a track means, this says where its
value lives.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager
from game_core import named_track


class WorldTrackManager(EntityManager):
    """Named world-level meters with bidirectional threshold reporting."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self._wsd = world_state_dir
        self.tracks_file = "world-tracks.json"

    def _load(self) -> Dict[str, Any]:
        return self.json_ops.load_json(self.tracks_file) or {}

    def _fire_crossings(self, name: str, result: Dict[str, Any]) -> List[str]:
        """Write consequences for thresholds crossed while CLIMBING.

        Climbing is the dangerous direction — the world learning something is an
        event that arrives, while the world forgetting is a slow condition. Firing
        both ways would put an incoherent beat in front of the GM every time a
        track decayed. Mirrors ThreatClockManager._fire_if_filled, including the
        stdout redirect: add_consequence announces itself, and this runs inside
        adjust(), whose --json output must stay parseable.
        """
        if result["after"] <= result["before"]:
            return []
        import contextlib
        from consequence_manager import ConsequenceManager

        fired = []
        with contextlib.redirect_stdout(sys.stderr):
            cm = ConsequenceManager(self._wsd)
            for threshold in result.get("crossed") or []:
                text = threshold.get("consequence")
                if not text:
                    continue
                fired.append(cm.add_consequence(
                    f"[Track — {name}] {text}",
                    trigger=f"the {name} track reached {threshold.get('at')}"))
        return fired

    def add_track(self, name: str, max_value: int, thresholds: List[Dict] = None,
                  note: str = None, current: int = 0) -> Dict[str, Any]:
        data = self._load()
        # Delegate clamping to named_track so it owns the [0, max] arithmetic.
        clamped_current = named_track(0, int(current),
                                      {"max": int(max_value), "thresholds": []})["after"]
        entry = {
            "current": clamped_current,
            "max": int(max_value),
            "thresholds": list(thresholds or []),
        }
        if note:
            entry["note"] = note
        data[name] = entry
        self.json_ops.save_json(self.tracks_file, data)
        return entry

    def adjust(self, name: str, delta: int) -> Optional[Dict[str, Any]]:
        """Apply delta, clamped to [0, max]. Returns the named_track result + name."""
        data = self._load()
        track = data.get(name)
        if track is None:
            return None
        result = named_track(
            int(track.get("current", 0)),
            int(delta),
            {"max": int(track.get("max", 0)),
             "thresholds": track.get("thresholds") or []},
        )
        track["current"] = result["after"]
        self.json_ops.save_json(self.tracks_file, data)
        return {"name": name, **result, "fired": self._fire_crossings(name, result)}

    def set_value(self, name: str, value: int) -> Optional[Dict[str, Any]]:
        """Set an absolute value, still reporting the thresholds it passes through."""
        track = self._load().get(name)
        if track is None:
            return None
        return self.adjust(name, int(value) - int(track.get("current", 0)))

    def remove_track(self, name: str) -> bool:
        data = self._load()
        if name in data:
            del data[name]
            self.json_ops.save_json(self.tracks_file, data)
            return True
        return False

    def get_tracks(self) -> Dict[str, Any]:
        return self._load()

    @staticmethod
    def render(tracks: Dict[str, Any]) -> str:
        """Filled/empty bars for the GM-visible context."""
        lines = []
        for name, t in tracks.items():
            cur, mx = int(t.get("current", 0)), int(t.get("max", 1))
            bar = "●" * cur + "○" * max(0, mx - cur)
            note = f" — {t['note']}" if t.get("note") else ""
            lines.append(f"{name}: [{bar}] {cur}/{mx}{note}")
        return "\n".join(lines)


def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="World tracks")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("add"); p.add_argument("name"); p.add_argument("max", type=int)
    p.add_argument("--current", type=int, default=0)
    p.add_argument("--note")
    p.add_argument("--thresholds-json",
                   help='[{"at": 3, "consequence": "..."}, ...]')

    p = sub.add_parser("adjust"); p.add_argument("name")
    p.add_argument("--delta", type=int, required=True)

    p = sub.add_parser("set"); p.add_argument("name")
    p.add_argument("--value", type=int, required=True)

    p = sub.add_parser("remove"); p.add_argument("name")
    sub.add_parser("list")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    m = WorldTrackManager()
    if args.action == "add":
        thresholds = None
        if args.thresholds_json:
            try:
                thresholds = json.loads(args.thresholds_json)
            except json.JSONDecodeError as e:
                sys.exit(emit_error(f"invalid --thresholds-json: {e}", json_mode))
        out = m.add_track(args.name, args.max, thresholds=thresholds,
                          note=args.note, current=args.current)
    elif args.action == "adjust":
        out = m.adjust(args.name, args.delta)
    elif args.action == "set":
        out = m.set_value(args.name, args.value)
    elif args.action == "remove":
        out = {"removed": m.remove_track(args.name)}
    else:
        out = m.get_tracks()

    if out is None:
        sys.exit(emit_error(f"no such track: {args.name}", json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2))
        if args.action == "list":
            print(WorldTrackManager.render(out))


if __name__ == "__main__":
    main()
