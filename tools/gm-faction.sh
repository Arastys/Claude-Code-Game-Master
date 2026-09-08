#!/bin/bash
# gm-faction.sh - Faction state (thin wrapper for faction_manager.py)
#
#   gm-faction.sh list                                Show all factions
#   gm-faction.sh add "Name" [--standing N] [--note "..."]
#   gm-faction.sh standing "Name" --set 2             Set standing (clamped -5..+5)
#   gm-faction.sh standing "Name" --delta -1          Adjust standing
#   gm-faction.sh member "Name" "NPC"                 Add a member
#   gm-faction.sh unmember "Name" "NPC"               Remove a member
#   gm-faction.sh claim "Name" "Location"             Claim territory
#   gm-faction.sh release "Name" "Location"           Drop a claim
#   gm-faction.sh relation "Name" "Other" hostile     How they regard another faction
#   gm-faction.sh holders "Location"                  Who claims this place
#   gm-faction.sh contested                           Ground claimed by more than one
#   gm-faction.sh remove "Name"                       Remove a faction
#
# `standing` is clamped to [-5,+5] and feeds game_core.reaction_roll directly.
# All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/faction_manager.py" "$@"
