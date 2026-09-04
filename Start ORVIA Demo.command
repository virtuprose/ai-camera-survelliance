#!/bin/zsh

set -e

project_dir="${0:A:h}"
cd "$project_dir"

bun_executable="$(command -v bun || true)"
if [[ -z "$bun_executable" ]]; then
  echo "Bun was not found. Open Terminal once, install Bun, and try again."
  read -r "?Press Return to close."
  exit 1
fi

(
  for attempt in {1..120}; do
    if /usr/bin/curl --fail --silent --max-time 1 http://localhost:3000/live >/dev/null 2>&1; then
      monitoring_state="$(/usr/bin/curl --fail --silent --max-time 1 http://127.0.0.1:8787/api/state 2>/dev/null || true)"
      if [[ "$monitoring_state" == *'"automaticMonitoring":"active"'* && "$monitoring_state" == *'"storage":"online"'* && "$monitoring_state" == *'"status":"passed"'* ]] || (( attempt >= 40 )); then
        /usr/bin/open http://localhost:3000/live
        exit 0
      fi
    fi
    /bin/sleep 0.5
  done
) &

exec "$bun_executable" run local
