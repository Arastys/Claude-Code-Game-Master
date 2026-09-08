#!/bin/bash
# gm-system.sh - Roll the kit's declared signature systems (wrapper for kit_systems.py)
#
#   gm-system.sh list                                  Show declared systems
#   gm-system.sh roll "<name>" [args]                  Execute one
#
#     named_track     --current N --delta N
#     price_roll      --severity N [--modifier N]
#     reaction_roll   --track-value N [--modifier N]
#     guarded_payoff  (no arguments)
#
# --modifier is a PER-ATTEMPT bonus and overrides the stored config value.
# All commands accept --json.

source "$(dirname "$0")/common.sh"

require_active_campaign

$PYTHON_CMD "$LIB_DIR/kit_systems.py" "$@"
