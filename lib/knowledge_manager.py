#!/usr/bin/env python3
"""
The knowledge ledger — who has actually been told what.

`facts.json` holds world truth: global, unowned, uncontested. This owns the
contested half. A proposition is a statement with a truth value; a stance is one
named entity's relationship to it. Deception needs no separate machinery — a
proposition marked `false` that someone holds as `knows` is a character who is
certain and wrong.

Nothing here decides who learns what. A stance is written when the fiction moves
information, the same way a faction standing is written when a bargain is kept.
There is no propagation and no inheritance: a faction's stance says nothing about
its members, because a ledger that infers knowledge nobody was given fails at the
one job it has.

Absence is `unaware` and is never stored, so recording ignorance — the common
case — costs nothing.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from entity_manager import EntityManager

TRUTHS = ("true", "false", "unresolved")
STANCES = ("knows", "suspects")
STATUSES = ("active", "dormant")
UNAWARE = "unaware"
BRIEF_LIMIT = 5


def _norm(value: Any) -> str:
    """Case-insensitive key, matching entity_manager.npcs_present."""
    return str(value or "").strip().lower()


def _one_of(value: Any, allowed: tuple, field: str) -> str:
    normalized = _norm(value)
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {allowed}, got {value!r}")
    return normalized


class KnowledgeManager(EntityManager):
    """Propositions, and who holds a stance on them."""

    def __init__(self, world_state_dir: str = None):
        super().__init__(world_state_dir)
        self._wsd = world_state_dir
        self.knowledge_file = "knowledge.json"

    def _load(self) -> Dict[str, Any]:
        data = self.json_ops.load_json(self.knowledge_file) or {}
        data.setdefault("next_id", 1)
        data.setdefault("propositions", {})
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.json_ops.save_json(self.knowledge_file, data)

    @staticmethod
    def _record_in(entry: Dict[str, Any], knower: str) -> Optional[Dict[str, Any]]:
        """The stance record this knower holds on this entry, or None."""
        needle = _norm(knower)
        for held, record in (entry.get("stances") or {}).items():
            if _norm(held) == needle:
                return record
        return None

    @staticmethod
    def _stance_in(entry: Dict[str, Any], knower: str) -> str:
        return (KnowledgeManager._record_in(entry, knower) or {}).get("stance", UNAWARE)

    def add_proposition(self, statement: str, truth: str = "unresolved",
                        about: str = None, status: str = "active",
                        session: int = 0) -> Dict[str, Any]:
        """Create a proposition and return it with its assigned id."""
        truth = _one_of(truth, TRUTHS, "truth")
        status = _one_of(status, STATUSES, "status")
        data = self._load()
        pid = f"P{data['next_id']}"
        data["next_id"] = int(data["next_id"]) + 1  # monotonic; ids are never reused
        entry = {
            "statement": str(statement),
            "truth": truth,
            "status": status,
            "touched": int(session),
            "stances": {},
        }
        if about:
            entry["about"] = str(about)
        data["propositions"][pid] = entry
        self._save(data)
        return dict(entry, id=pid)

    def set_stance(self, pid: str, knower: str, stance: str,
                   source: str = None, session: int = 0) -> Optional[Dict[str, Any]]:
        """Record that this entity knows or suspects. Replaces any earlier stance."""
        stance = _one_of(stance, STANCES, "stance")
        data = self._load()
        entry = data["propositions"].get(pid)
        if entry is None:
            return None
        record = {"stance": stance, "since": int(session)}
        if source:
            record["source"] = str(source)
        stances = entry.setdefault("stances", {})
        for held in [k for k in stances if _norm(k) == _norm(knower)]:
            del stances[held]
        stances[knower] = record
        entry["touched"] = int(session)
        self._save(data)
        return dict(entry, id=pid)

    def forget(self, pid: str, knower: str) -> Optional[Dict[str, Any]]:
        """Remove a stance, returning that knower to `unaware`."""
        data = self._load()
        entry = data["propositions"].get(pid)
        if entry is None:
            return None
        stances = entry.setdefault("stances", {})
        for held in [k for k in stances if _norm(k) == _norm(knower)]:
            del stances[held]
        self._save(data)
        return dict(entry, id=pid)

    def stance_of(self, pid: str, knower: str) -> str:
        """`knows`, `suspects`, or `unaware`. Unaware is never stored."""
        return self._stance_in(self._load()["propositions"].get(pid) or {}, knower)

    def set_status(self, pid: str, status: str) -> Optional[Dict[str, Any]]:
        status = _one_of(status, STATUSES, "status")
        data = self._load()
        entry = data["propositions"].get(pid)
        if entry is None:
            return None
        entry["status"] = status
        self._save(data)
        return dict(entry, id=pid)

    def get_propositions(self) -> Dict[str, Any]:
        return self._load()["propositions"]

    def who_knows(self, needle: str) -> Dict[str, Any]:
        """Resolve by exact id first, else by case-insensitive substring of the
        statement. A substring matching several returns all of them rather than
        guessing which was meant."""
        props = self.get_propositions()
        if needle in props:
            return {needle: props[needle]}
        n = _norm(needle)
        return {pid: e for pid, e in props.items()
                if n and n in _norm(e.get("statement"))}

    def held_by(self, knower: str) -> Dict[str, Any]:
        """Every proposition this entity holds a stance on, with that stance.

        Named `held_by` rather than `knows` so the verb never collides with the
        stance value of the same name.
        """
        out = {}
        for pid, entry in self.get_propositions().items():
            stance = self._stance_in(entry, knower)
            if stance != UNAWARE:
                out[pid] = dict(entry, id=pid, stance=stance)
        return out


def _current_session() -> int:
    """The live session number, or 0 if it cannot be read.

    Imported lazily: session_manager is a large module and the ledger itself has
    no need of it. Never read `session_count` from campaign-overview.json —
    campaign_manager writes it once at creation and nothing increments it.
    """
    try:
        from session_manager import SessionManager
        return SessionManager().session_number()
    except Exception:
        return 0


def main():
    import argparse
    import json
    from cli_output import wants_json, strip_json_flag, emit, emit_error

    parser = argparse.ArgumentParser(description="The knowledge ledger")
    sub = parser.add_subparsers(dest="action")

    p = sub.add_parser("add"); p.add_argument("statement")
    p.add_argument("--truth", choices=TRUTHS, default="unresolved")
    p.add_argument("--about")
    p.add_argument("--status", choices=STATUSES, default="active")
    p = sub.add_parser("stance"); p.add_argument("pid"); p.add_argument("knower")
    p.add_argument("stance", choices=STANCES); p.add_argument("--source")
    p = sub.add_parser("forget"); p.add_argument("pid"); p.add_argument("knower")
    p = sub.add_parser("who-knows"); p.add_argument("needle")
    p = sub.add_parser("held-by"); p.add_argument("knower")
    p = sub.add_parser("status"); p.add_argument("pid")
    p.add_argument("status", choices=STATUSES)
    p = sub.add_parser("list")
    p.add_argument("--active", action="store_true")
    p.add_argument("--dormant", action="store_true")

    json_mode = wants_json()
    args = parser.parse_args(strip_json_flag(sys.argv[1:]))
    if not args.action:
        parser.print_help(); sys.exit(1)

    m = KnowledgeManager()
    session = _current_session()

    if args.action == "add":
        out = m.add_proposition(args.statement, truth=args.truth,
                                about=args.about, status=args.status,
                                session=session)
    elif args.action == "stance":
        out = m.set_stance(args.pid, args.knower, args.stance,
                           source=args.source, session=session)
    elif args.action == "forget":
        out = m.forget(args.pid, args.knower)
    elif args.action == "who-knows":
        out = m.who_knows(args.needle)
    elif args.action == "held-by":
        out = m.held_by(args.knower)
    elif args.action == "status":
        out = m.set_status(args.pid, args.status)
    else:
        props = m.get_propositions()
        if args.active:
            props = {k: v for k, v in props.items() if v.get("status") == "active"}
        elif args.dormant:
            props = {k: v for k, v in props.items() if v.get("status") == "dormant"}
        out = props

    if out is None:
        sys.exit(emit_error(f"no such proposition: {args.pid}", json_mode))

    if json_mode:
        emit(out, json_mode=True)
    else:
        print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
