#!/bin/zsh
# Overseer watcher: every 60 s read the roster, re-render the dashboard, notify on a new `waiting`.
# Start once in a spare terminal:  zsh overseer/watch.sh
set -u
here="${0:A:h}"
interval="${1:-60}"
while true; do
  python3 "$here/roster.py" --out "$here/roster.json" --notify
  python3 "$here/render.py" --state "$here/state.json" --roster "$here/roster.json" --out "$here/dashboard.html" 2>/dev/null
  sleep "$interval"
done
