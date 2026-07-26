#!/usr/bin/env bash
# Fire a sample /test request at your locally-running agent (no signature needed
# when SITREP_AGENT_SECRET is unset). Run scripts/run-local.sh first.
#
# Tip: run twice with the second payload in fixtures/meeting2 to see drift —
# or use: python scripts/demo_driftguard.py
set -euo pipefail
curl -s -X POST http://localhost:9000/test \
  -H 'Content-Type: application/json' \
  -d '{
    "task": {"id": "t-drift-1", "title": "DriftGuard review", "description": "workspace: smoke-test"},
    "summary": "Growth standup. Priya reported activation at 45%. She defined activation as a new user who signs up and verifies their email within 24 hours. Marketing will use the same definition for campaign reporting.",
    "attendees": [{"id": "a1", "name": "Priya"}, {"id": "a2", "name": "Jordan"}],
    "agent": {"instructions": "workspace: smoke-test", "tools": [], "model": "llama3.1"}
  }' | python3 -m json.tool
