# Release notes — v0.1.0

> Initial public release. Use this file as `--notes-file` for `gh release create v0.1.0`.

---

## What's new

`hermes-cloudflare-access` is a dashboard auth provider for Hermes Agent that trusts the `Cf-Access-Jwt-Assertion` header (and `CF_Authorization` cookie) injected by Cloudflare Zero Trust. If your Hermes dashboard already sits behind a Cloudflare Tunnel with an Access policy, this plugin turns the edge-authenticated session into a Hermes session cookie in one redirect — no second password, no OAuth detour.

### Highlights

- ✅ Drop-in third dashboard auth option alongside `basic` and `nous`.
- ✅ RS256 signature verification against the team JWKS, with a 5-minute in-process cache that serves stale keys on refresh failure.
- ✅ Strict claim validation: `aud` (mandatory), `iss` (team URL match), `exp`, `nbf`.
- ✅ Same HMAC-signed `Session` cookies the `basic` and `nous` providers use — no extra session scheme to learn.
- ✅ Configurable TTL and HMAC secret (set `dashboard.cloudflare_access.secret` for stable sessions across restarts).
- ✅ Same-origin-only `next=` sanitisation on the redirect.
- ✅ Bundled-plugin and user-plugin install paths.
- ✅ Test suite with synthetic-JWT shim — CI runs on Python 3.10 / 3.11 / 3.12 against `NousResearch/hermes-agent` installed editable.

### Install

```bash
pip install hermes-cloudflare-access
```

Then apply the one-file middleware allowlist patch (8 lines) from `examples/middleware-public-prefix.patch`, copy the bundled plugin into your Hermes plugin tree, set `team` + `aud`, and restart. Full instructions in [`README.md`](https://github.com/rnagarajanmca/hermes-cloudflare-access#install).

### Known limitations

- Hermes 0.20.0 has no plugin-contributed public-path API; install requires the bundled middleware patch. Upstream PR pending.
- JWKS cache is per-process (multi-worker deployments each fetch once on startup).
- No token-refresh flow; when the Access JWT expires the user re-auths at the edge.

### Acknowledgements

Tested against `NousResearch/hermes-agent` `main` at the time of release. Bug reports and PRs welcome — see [`CONTRIBUTING.md`](https://github.com/rnagarajanmca/hermes-cloudflare-access/blob/main/CONTRIBUTING.md).

---

**Full Changelog**: https://github.com/rnagarajanmca/hermes-cloudflare-access/blob/main/CHANGELOG.md