#!/bin/bash
# run_implementation.sh — Run all three implementation sessions sequentially.
#
# Usage:
#   cd quicknxsv1
#   bash prompts/run_implementation.sh
#
# Each session starts a fresh Claude context, reads the plan, implements its
# phases via TDD, commits, and checkpoints progress in MEMORY.md for the next
# session to pick up.
#
# Prerequisites:
#   - claude CLI installed and authenticated
#   - pixi environment set up (pixi install)
#   - sshfs mounts at /SNS/REF_M and /SNS/REF_L accessible
#   - Phases 1-9 plan at plan/read-event-nexus-h5.md (reviewed)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

##echo "=== Session 1: Helpers, Metadata, Core (Phases 1-3) ==="
##echo "Starting at $(date)"
##claude -p "$(cat prompts/session1-helpers-metadata-core.md)" \
##    --dangerously-skip-permissions \
##    --model claude-opus-4-6 \
##    --max-turns 100
##echo "Session 1 completed at $(date)"
##echo ""

echo "=== Session 2: File Search, Splitting, Compat (Phases 4-7) ==="
echo "Starting at $(date)"
claude -p "$(cat prompts/session2-search-splitting-compat.md)" \
    --dangerously-skip-permissions \
    --model claude-opus-4-6 \
    --max-turns 100
echo "Session 2 completed at $(date)"
echo ""

echo "=== Session 3: Dead-Time, Polarization (Phases 8-9) ==="
echo "Starting at $(date)"
claude -p "$(cat prompts/session3-deadtime-polarization.md)" \
    --dangerously-skip-permissions \
    --model claude-opus-4-6 \
    --max-turns 100
echo "Session 3 completed at $(date)"
echo ""

echo "=== All sessions complete ==="
echo "Check git log for commits and MEMORY.md for final status."
git log --oneline -10
