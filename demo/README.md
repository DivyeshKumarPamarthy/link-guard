# Demo server

A small Starlette app that imitates good, bad and broken download servers, so LinkGuard's
tests and the demo run offline with no real malware (`docs/phase1-spec.md` §11).

```zsh
make demo-server   # from the repo root
```

| Listener | Port | Certificate |
| --- | --- | --- |
| HTTP | 8081 | none |
| HTTPS | 8443 | valid for `a.demo.test`, `b.demo.test`, `c.demo.test` (local test CA) |
| HTTPS | 8444 | issued for `wrong-host.example`: clients connecting as a demo host must refuse it |

All listeners bind to `127.0.0.1` only. The demo hostnames are not in DNS: the backend maps
them to 127.0.0.1 with `LG_STATIC_HOSTS` in the `test`/`demo` profile. To try them with curl:
`curl --resolve a.demo.test:8081:127.0.0.1 http://a.demo.test:8081/page`.

On first start, a throwaway test CA and certificates are generated into `demo/certs/`
(gitignored). The CA's private key is never saved. Delete the folder to regenerate.

Samples for `/f/{name}`, `/gzip/{name}`, `/disguised/{name}` and `/cd/{variant}` come from
`samples/`. Run `make samples` first: `make_samples.py` builds harmless files for every format
plus the disguised copies, the same bytes on every run (`samples/SHA256SUMS`). See
`docs/modules/samples.md`.

Settings: `DEMO_*` environment variables, see `demo_server/config.py` (ports, sizes, timings).
Endpoints and their purpose: `docs/modules/demo-server.md`.
