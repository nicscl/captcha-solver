#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ../.env; set +a
python3 cli.py "$@"
