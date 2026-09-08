# Knowledge Ledger — Spec

**Date:** 2026-09-08
**Found by:** asking what a campaign built on concealment needs that does not exist yet.

## The governing principle

The engine holds no game's concepts. A World Kit declares what its world runs on;
the engine renders and resolves without understanding any of it. Every change here
must be expressible by a world that has never heard of vampires and equally by one
that has never heard of D&D.

## The gap

The world state can say a thing is true. It cannot say who believes it.

`facts.json` holds world truth: global, unowned, uncontested. `npcs.json` gives each
NPC an `events` list — a timestamped record of what happened to or around them — and
a single free-text `secret`, the one thing that character is hiding. `factions.json`
holds standing, membership, territory and relations between organisations.

None of these is a proposition that different parties can hold different versions of.
There is no way to record that Eurgain believes the child drowned, that Y Bleiddiaid
know she was taken, and that the truth is neither. The scene brief already prints
`has a secret` for an NPC with one — existence only, never the text — so the engine
already understands that some knowledge is withheld from its own reader. It has
nowhere to put the rest of that idea.

The cost is paid by the GM. Without a ledger, an NPC's knowledge lives only in the
narrative history, and the failure is silent: a character reacts to something nobody
ever told them, and the world stops being one that can keep a secret.

## What this is

A ledger of **propositions** and **stances**, written by hand.

A proposition is a statement with a truth value. A stance is one named entity's
relationship to that statement. The engine never decides who learns what. Stances are
written when the fiction moves information, the same way a faction standing is written
when a bargain is kept.

The truth value is what makes deception free. A proposition marked `false` that a
character holds as `knows` is someone who is certain and wrong. That requires no
separate machinery for lies, rumour or misinformation: they are all a false
proposition someone believes.

## Data model

```
proposition
  id          short stable identifier: P + one above the highest existing
              number, never reused after a proposition is deleted
  statement   the claim, in plain language
  truth       true | false | unresolved
  about       optional — the entity the statement concerns
  status      active | dormant
  touched     session number from campaign-overview.json, stamped on every write

stance  (proposition x knower)
  knower      any name: an NPC, a faction, or the player character
  stance      knows | suspects
  source      free text — "observed", "told by Eurgain", "overheard at the ford"
  since       session number
```

**Absence is `unaware`.** No stored record means the entity does not know, and the
brief renders that. Recording ignorance costs nothing, which matters because
ignorance is the common case.

**Any named entity can hold a stance, and there is no inheritance.** A faction knowing
something is a record separate from any member knowing it, because an organisation can
hold intelligence its rank and file have never heard. The brief surfaces the tension —
a member unaware of what their own faction knows — without asserting that the member
knows it. Inheritance would make the ledger assert knowledge nobody was ever given,
which is the precise failure this system exists to prevent.

**`about` is not decoration.** It lets the brief report that a live proposition
concerns a present character who is themselves unaware of it. That is the shape of
most dramatic irony, and it is invisible without the field.

## Storage and module

A new `knowledge.json` per campaign, a new `lib/knowledge_manager.py`, and one wrapper
`tools/gm-know.sh`. This mirrors `factions.json` / `lib/faction_manager.py` /
`tools/gm-faction.sh` exactly, so it inherits a structure that is already reviewed,
tested and understood.

Two alternatives were considered and rejected. Storing stances on each NPC record makes
"who knows this" a scan across every NPC, and factions are not NPCs. Extending
`facts.json` with holders merges world truth and contested belief into one file, which
destroys the distinction the system exists to draw.

## Tool surface

```
gm-know.sh add "<statement>" --truth true|false|unresolved [--about X] [--status active|dormant]
gm-know.sh stance <id> "<knower>" knows|suspects [--source "..."]
gm-know.sh forget <id> "<knower>"
gm-know.sh who-knows <id|substring>
gm-know.sh held-by "<knower>"
gm-know.sh list [--active|--dormant]
gm-know.sh status <id> active|dormant
```

Every verb takes `--json`. Every verb gets a wrapper-level subprocess test. That second
rule is not boilerplate: a previous plan added a verb to a wrapper that dispatches on a
`case` statement rather than passing arguments through, so the new verb printed usage
and exited 0. It passed three review gates before the final whole-branch review caught
it. A test that drives the wrapper as a subprocess is the only thing that catches it.

## Rendering in the scene brief

A block appended near NPC VOICES, silent when the ledger holds nothing:

```
--- WHO KNOWS WHAT (present) ---
P4  "Rhiannon does not age"  (true)
    Mair          KNOWS      s5, told by Eurgain
    Gwen          unaware
    Y Bleiddiaid  KNOWS   - Mair's own kin do not
P7  "the child drowned"  (FALSE)
    Mair          KNOWS      s2, told by Rhiannon
    Gwen          suspects   s6, observed
2 dormant propositions not shown.
```

A proposition is shown when it is `active` **and** relevant to the room: some present
NPC holds a stance on it, or its `about` entity is present. Relevance is what makes the
block short — an active proposition concerning people who are nowhere near this scene
stays silent until they walk on.

Within that set, the five most recently touched are shown. Every present NPC renders
under each shown proposition, defaulting to `unaware`. Dormant propositions stay in the
ledger and surface on query.

The block must be in the brief rather than available on demand. A discipline tool that
catches the GM only when the GM remembers to ask fails at exactly the moment it exists
for.

## The player character's stances

The player character is a knower like any other. There is no player-facing journal and
no player-facing query; the obligation lands on narration.

When the PC is about to act on a proposition she holds as `suspects` rather than
`knows`, the GM says so in the fiction — that she is fairly sure, though no one has
actually told her. When she is certain of a proposition the ledger marks `false`, the
GM writes her as certain and lets the world correct her.

The visible output of this system is prose that is more careful about what a character
has actually been told.

## Kit-agnosticism

Nothing in `lib/` learns a campaign concept. `unaware / suspects / knows` are engine
primitives, and the distinction from `AC` or `generation` is real: those are one game's
vocabulary, while these are properties of any fiction containing people who can be told
things. A world that wants none of this creates no propositions and sees no block.
There is no kit flag and no declaration to make — an empty ledger is silent.

## Requirements

1. A proposition can be created with a statement, a truth value of `true`, `false` or
   `unresolved`, an optional `about` entity, and a status of `active` or `dormant`.
   It receives a short stable id.
2. A stance of `knows` or `suspects` can be set for any named knower on any
   proposition, with an optional free-text source. Setting a stance stamps the
   proposition's `touched` session and the stance's `since` session.
3. A stance can be removed, returning that knower to `unaware`.
4. A knower with no stance record on a proposition is `unaware`. This is never stored.
5. `who-knows` reports every stance on a proposition, resolved by id or by
   case-insensitive substring of the statement. A substring matching more than one
   proposition reports all of them rather than guessing. `held-by` reports every
   proposition one entity holds; the verb is deliberately not named `knows`, which
   would collide with the stance value of the same name.
6. A proposition's status can be moved between `active` and `dormant`.
7. The scene brief renders a WHO KNOWS WHAT block for the active propositions
   relevant to the room — those on which a present NPC holds a stance, or whose
   `about` entity is present — showing the five most recently touched, every present
   NPC under each, and a count of the dormant remainder. The block is absent entirely
   when no proposition qualifies. Present NPCs are resolved by the same means the
   brief already uses for NPC VOICES.
8. Every wrapper verb returns structured output under `--json` and is exercised by a
   subprocess test against the wrapper, not only against the Python manager.

## Non-goals

- **Automatic propagation.** Information does not move between sessions on a tick, and
  does not spread along faction relation edges. The GM moves it.
- **Faction-to-member inheritance.** Ruled out above; it would have the ledger assert
  knowledge nobody was given.
- **A player-facing journal or query.** The player's view is the GM's narration.
- **Rolled espionage.** No `game_core` primitive for acquiring information against
  resistance. Spying, interrogation and surveillance are played out in fiction and
  their outcomes written to the ledger by hand. The ledger is the deliverable; a dice
  layer on top of it is a separate decision for a later day.
- **Promoting a proposition into `facts.json`** when it becomes common knowledge.
- **Migrating the per-NPC `secret` string.** It stays as the prose hook for an NPC's
  inner life. The overlap is real and deliberate: `secret` is one line of character
  authoring, the ledger is machine-readable belief. Anyone extending either should
  know the other exists.

## Acceptance

Every requirement is tested against at least three kits — `dnd5e`, the resource-axis
DCC fixture, and a `custom` kit — using the existing `_make_world(tmp_path, slug,
ruleset)` builder in `tests/test_kit_vitals.py`. A change that works for only one of
them has not met the bar.

The brief-rendering requirement is additionally tested for silence: a world with an
empty ledger produces a scene brief containing no WHO KNOWS WHAT text at all.
