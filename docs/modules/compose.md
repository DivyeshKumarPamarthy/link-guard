# Module: Localhost-only exposure and docker-compose (X3/X4, task T2.5)

Owner: TBD · Reviewer: TBD · Phase: A · Last updated: 2026-10-24

## What it does (2–3 sentences, plain language)

Keeps the backend reachable from this machine only. Run directly, the API binds `127.0.0.1`;
run with `make dev` (Docker Compose), the API, web app and demo server publish their ports on
`127.0.0.1` only. A test fails if anyone changes the compose file to publish a port on every
network interface.

## Inputs and outputs
- Input: `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `demo/Dockerfile`.
- Output: `make dev` = `docker compose up --build`: API on <http://127.0.0.1:8000>, web on
  <http://127.0.0.1:5173>, demo server on 127.0.0.1 ports 8081 (HTTP), 8443 and 8444 (HTTPS).

## How it works (5–10 lines; the steps you would draw on a whiteboard)

1. Without Docker, `python -m app` binds `LG_BIND_HOST` (default `127.0.0.1`, T0.7); the demo
   server binds `DEMO_BIND_HOST` (default `127.0.0.1`, T1.1).
2. Each image installs dependencies from its lock file (`uv sync --locked --no-dev`, `npm ci`).
3. Inside a container, `127.0.0.1` is the container's own loopback: Docker's port forwarding
   cannot reach it. So compose sets `LG_BIND_HOST=0.0.0.0`, `DEMO_BIND_HOST=0.0.0.0` and runs
   Vite with `--host 0.0.0.0` (D31).
4. On the host side, every port is written as `"127.0.0.1:<host>:<container>"`, so Docker
   listens on the Mac's loopback only. Other machines on the network cannot connect.
5. `test_compose_ports.py` loads the compose file with `yaml.safe_load` and checks every port of
   every service: the string form must start with `127.0.0.1:`, the long form must have
   `host_ip: 127.0.0.1`, a bare number is refused, and so is `network_mode: host`.

## Why it is designed this way (the decision and the simpler/harder alternative you rejected)

- **Loopback only (D18)**: the backend has no login, open CORS and no rate limits (D17) and makes
  outbound requests to any link. Reachable from the network, it would be an open proxy.
- **`0.0.0.0` inside, `127.0.0.1` outside (D31)**: the only setup where the published port works
  and still is not public. Rejected: `network_mode: host` (behaves differently on Docker
  Desktop for Mac than on Linux, and would expose whatever the container listens on).
- **A test, not a reviewer's eye**: `8000:8000` looks harmless and is Docker's usual example.
  The test runs in `make test` and CI, so the mistake cannot be merged by accident.
- **The test reads YAML instead of running Docker**: tests must work without Docker and without
  the network; reading the file is enough to check what Docker will publish.
- **No Dockerfile hardening**: non-root user, read-only filesystem and limits are Phase E.

## How it is tested (test files, acceptance rows it covers)

- `backend/tests/unit/test_compose_ports.py`: the real compose file publishes only loopback
  ports and exactly the expected ones (api 8000, web 5173, demo 8081/8443/8444); the servers
  listen on `0.0.0.0` inside the containers; the checker refuses `8000:8000`,
  `0.0.0.0:8000:8000`, `8000`, a YAML number, `127.0.0.10:…`, `[::]:…`, the long form without
  `host_ip` or with `0.0.0.0`, one bad port among good ones and `network_mode: host`.
- `backend/tests/unit/test_config.py`: `LG_BIND_HOST` defaults to `127.0.0.1`.
- Task T2.5 acceptance: "a test fails if compose publishes any port without the `127.0.0.1:`
  prefix".

## Known limitations

- The `docker compose` stack itself was not started by the automated task run (no Docker in that
  environment); start it once with `make dev` to check the images build.
- The API in compose runs in the `dev` profile, so it refuses the demo server's addresses
  (correctly: no SSRF exemptions in `dev`). Scanning demo links from the compose stack needs the
  `demo` profile and a way for the API container to reach the demo container; not decided yet.
- Scans are stored in the API container (`/app/linkguard.db`) and disappear when the container
  is removed.
- The containers run as root; hardening is Phase E.

## Likely viva questions (and your short answers)

- *Why not just `8000:8000`?* That publishes on every interface (`0.0.0.0`) of the host, so
  anyone on the same Wi-Fi could use our anonymous backend to make requests.
- *Then why does the API bind `0.0.0.0` in Docker?* That is inside the container's own network.
  Docker forwards the host's `127.0.0.1:8000` to the container's interface, not to its loopback.
  The host side is what other machines see, and it is loopback only.
- *How do you stop someone changing it later?* `test_compose_ports.py` runs in `make test` and CI
  and fails on any port not published on `127.0.0.1`.
- *Why is `network_mode: host` refused?* It skips port publishing entirely, so every listener in
  the container would be on the host's network.
- *Why `yaml.safe_load`?* Plain `yaml.load` can build arbitrary Python objects from tags;
  `safe_load` only builds plain data.
