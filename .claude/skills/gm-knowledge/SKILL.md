---
name: gm-knowledge
description: The knowledge ledger — who has actually been told what. Load when information moves (someone witnesses, confesses, lies, overhears, or is deliberately kept in the dark), when you are about to have an NPC act on something, or when the WHO KNOWS WHAT block shows a stance you are unsure how to play.
---

# Who Knows What

The ledger exists to stop one specific failure: an NPC reacting to information
nobody ever gave them. That failure is silent — nothing crashes, the scene just
quietly stops being a world that can keep a secret.

## The model

A **proposition** is a statement with a truth value. A **stance** is one named
entity's relationship to it: `knows`, `suspects`, or — by having no record at all
— `unaware`.

A lie needs no special machinery. A proposition marked `false` that someone holds
as `knows` is a character who is certain and wrong. Write the falsehood as its own
proposition; do not try to encode the deception on the true one.

Knowers are NPCs, factions, or the PC. **There is no inheritance.** A faction
knowing something says nothing about any member, and you must never play a member
as knowing because their faction does. The brief will show you the gap; closing it
is a scene, not a lookup.

## When to write

Write a stance the moment the fiction moves information, before you narrate:

| What happened | Command |
|---|---|
| Someone witnessed it | `bash tools/gm-know.sh stance P4 "Mair" knows --source "saw it at the ford"` |
| Someone was told | `bash tools/gm-know.sh stance P4 "Mair" knows --source "told by Eurgain"` |
| Someone half-caught it | `bash tools/gm-know.sh stance P4 "Gwen" suspects --source "overheard"` |
| A new secret enters play | `bash tools/gm-know.sh add "<the claim>" --truth true --about "Rhiannon"` |
| Someone believes a lie | `bash tools/gm-know.sh add "<the lie>" --truth false` then a `knows` stance on the dupe |
| They were wrong, or it was retconned | `bash tools/gm-know.sh forget P4 "Mair"` |
| The thread is spent | `bash tools/gm-know.sh status P4 dormant` |

Before a scene where it matters: `bash tools/gm-know.sh who-knows "<substring>"` for one
proposition, `bash tools/gm-know.sh held-by "Mair"` for one person.

**Do not seed a ledger ahead of play.** Same rule as the anti-gazetteer rule for
locations: a proposition exists once it is in play, not because it might be later.

## Reading the block

`--- WHO KNOWS WHAT (present) ---` shows the active propositions relevant to this
room — someone here holds a stance, or the statement is about someone here. The
useful signal is the `unaware` lines. Read them as a list of things the person in
front of the player cannot say, cannot react to, and would be surprised by.

`(FALSE)` beside a statement someone `KNOWS` is the single most playable line in
the block. That character is confident. Play them confident.

A faction line ending `— Mair does not` means the organisation holds something its
own member has not been told. That is a scene waiting to happen, not a bookkeeping
note.

## Narrating the PC's own stances

The player has no view of this ledger, so their character's stances land entirely
in your prose.

- The PC holds `suspects`: never write her as certain. Say the doubt out loud —
  she is fairly sure, though no one has actually told her.
- The PC holds `knows` on a proposition marked `false`: write her as certain, and
  let the world correct her. Do not hedge on her behalf, and do not wink at the
  player.
- The PC is `unaware`: she cannot act on it. If the player acts on it anyway,
  that is the player knowing something their character does not — resolve it in
  the fiction rather than by quietly granting her the knowledge.

## What this does not do

Information does not spread on its own. There is no tick, no propagation along
faction relations, and no roll for spying. Espionage is played out in fiction and
its outcome written here by hand.
