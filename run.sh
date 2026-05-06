#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "${1:-}" = "gate" ]; then
  shift
  exec python3 quality_gate.py "$@"
fi
set -a; . ../.env; set +a
python3 cli.py "$@"
