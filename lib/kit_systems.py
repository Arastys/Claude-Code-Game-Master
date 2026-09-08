#!/usr/bin/env python3
"""
Roll the kit's declared signature systems.

ruleset.json `systems` entries are instantiations of a game_core primitive, and
scene context tells the GM every beat to ROLL them rather than narrate them. There
was no way to do that: game_core is a pure library with no CLI, and no wrapper
invoked it. This resolves a system by name and dispatches it to its primitive with
the stored config.

The primitives stay pure — this module supplies the per-attempt arguments the
config cannot know (a track's current value, an attempt's severity, a reputation
score) and returns the primitive's own result untouched.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from world_kit import WorldKit
from game_core import named_track, price_roll, reaction_roll, guarded_payoff


class KitSystems:
    """Resolve and execute the active kit's declared signature systems."""

    def __init__(self, world_state_dir: str = None):
        self.kit = WorldKit(world_state_dir)

    def list_systems(self) -> List[Dict[str, Any]]:
        return self.kit.systems()

    def find(self, name: str) -> Optional[Dict[str, Any]]:
        needle = (name or "").strip().lower()
        for system in self.list_systems():
            if str(system.get("name", "")).strip().lower() == needle:
                return system
        return None

    def roll(self, name: str, *, current: int = None, delta: int = None,
             severity: int = None, track_value: int = None,
             modifier: int = None, rng: Any = None) -> Dict[str, Any]:
        system = self.find(name)
        if system is None:
            raise KeyError(f"no declared system named {name!r}")
        primitive = system.get("primitive")
        config = dict(system.get("config") or {})
        if modifier is not None:
            config["modifier"] = int(modifier)

        if primitive == "named_track":
            if current is None or delta is None:
                raise ValueError("named_track needs --current and --delta")
            result = named_track(int(current), int(delta), config)
        elif primitive == "price_roll":
            if severity is None:
                raise ValueError("price_roll needs --severity")
            result = price_roll(int(severity), config, rng=rng)
        elif primitive == "reaction_roll":
            if track_value is None:
                raise ValueError("reaction_roll needs --track-value")
            result = reaction_roll(int(track_value), config, rng=rng)
        elif primitive == "guarded_payoff":
            result = guarded_payoff(config, rng=rng)
        else:
            raise ValueError(f"unknown primitive {primitive!r} on system {name!r}")

        return {"system": system.get("name"), "primitive": primitive, **result}


def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="Roll the kit's signature systems")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("list")
    p = sub.add_parser("roll")
    p.add_argument("name")
    p.add_argument("--current", type=int)
    p.add_argument("--delta", type=int)
    p.add_argument("--severity", type=int)
    p.add_argument("--track-value", dest="track_value", type=int)
    p.add_argument("--modifier", type=int, help="per-attempt bonus; overrides config")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    ks = KitSystems()
    if args.action == "list":
        out = ks.list_systems()
    else:
        try:
            out = ks.roll(args.name, current=args.current, delta=args.delta,
                          severity=args.severity, track_value=args.track_value,
                          modifier=args.modifier)
        except KeyError as exc:
            sys.exit(emit_error(exc.args[0], json_mode))
        except ValueError as exc:
            sys.exit(emit_error(str(exc), json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
