#!/bin/bash
# gm-know.sh - The knowledge ledger (thin wrapper for knowledge_manager.py)
#
#   gm-know.sh add "<statement>" [--truth true|false|unresolved] [--about "X"] [--status active|dormant]
#   gm-know.sh stance P4 "Mair" knows|suspects [--source "told by Eurgain"]
#   gm-know.sh forget P4 "Mair"              Return them to unaware
#   gm-know.sh who-knows P4|"substring"      Every stance on a proposition
#   gm-know.sh held-by "Mair"                Everything one entity holds
#   gm-know.sh list [--active|--dormant]     All propositions
#   gm-know.sh status P4 active|dormant      Retire it, or wake it up
#
# A proposition is a statement with a truth value; a stance is one entity's
# relationship to it. A `false` proposition someone `knows` is how a lie is
# stored. Absence is `unaware` — never record that someone does not know.
# Knowers are NPCs, factions, or the PC, and there is NO inheritance: a faction
# knowing something says nothing about its members.
# All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/knowledge_manager.py" "$@"
