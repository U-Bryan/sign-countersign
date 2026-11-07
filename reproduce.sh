#!/usr/bin/env sh
# Mac/Linux wrapper: ./reproduce.sh [--mock-full | --full --budget 60]
export PYTHONUTF8=1
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/.venv/bin/python" "$DIR/reproduce.py" "$@"
