#!/bin/sh
# Run by cron every 30 minutes: check every portal, commit the new data
# and push it. If a push fails, the commit stays local and goes out next run.
set -eu
cd "$(dirname "$0")/.."

exec 9>/tmp/monitoreo-publico.lock
flock -n 9 || exit 0

python3 monitor/check.py
git add data
git commit -q -m "Chequeo $(TZ=America/Argentina/Buenos_Aires date +%Y-%m-%dT%H:%M)" || exit 0
git pull -q --rebase origin main
git push -q origin main
