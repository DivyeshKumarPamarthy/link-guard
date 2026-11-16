#!/bin/sh
# The one-command demo (task T4.2). Run it with `make demo`.
#
# It starts three programs on this computer, with no Docker and no internet:
#   1. the demo server (pretend download sites)   127.0.0.1:8081, :8443, :8444
#   2. the API in the demo profile (demo/demo.env) 127.0.0.1:8000
#   3. the web app with the demo links             127.0.0.1:5173
# Press Ctrl-C to stop all three.
#
# Docker (`make dev`) cannot run the demo: it uses the dev profile, which rightly refuses
# the demo server's ports and private address.
set -eu
cd "$(dirname "$0")/.."

# uv must not look anything up online: the demo has to work with Wi-Fi off.
# If this fails, run `make setup` once while online.
export UV_OFFLINE=1

# A port that is already taken would make one program fail while the others start, and the
# web app would then talk to whatever else is listening on port 8000. Stop early instead.
for port in 8000 5173 8081 8443 8444; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "make demo: port $port is already in use. Stop this program first:" >&2
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2
    exit 1
  fi
done

pids=""
stop_all() {
  trap - INT TERM EXIT
  # shellcheck disable=SC2086  # the list of process ids must be split into words
  kill $pids 2>/dev/null || true
}
trap stop_all INT TERM EXIT

(cd demo && exec uv run python -m demo_server) &
pids="$pids $!"

# `set -a` exports every variable the file sets, so the API started below receives them.
(set -a && . demo/demo.env && set +a && cd backend && exec uv run python -m app) &
pids="$pids $!"

(cd web && exec npm run dev:demo -- --host 127.0.0.1 --port 5173 --strictPort) &
pids="$pids $!"

echo "LinkGuard demo: open http://127.0.0.1:5173 (Ctrl-C stops everything)"
wait
