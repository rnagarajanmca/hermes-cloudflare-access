# hermes-cloudflare-access

Dashboard auth provider for [Hermes Agent](https://hermes-agent.nousresearch.com/)
that trusts the `Cf-Access-Jwt-Assertion` header (and `CF_Authorization`
cookie) injected by **Cloudflare Zero Trust**.

If you run Hermes behind a Cloudflare Tunnel with an Access policy on the
hostname, this plugin skips Hermes's own password flow entirely. Cloudflare
handles auth at the edge (email OTP, Google, Okta, whatever you wire up),
this plugin mints a Hermes session from the validated JWT.

```
browser --CF-Access-JWT--> hermes --session--> browser
   ^
   | email OTP / IdP
cloudflare edge
```

## Why

Hermes ships with two auth options:

- `basic` — username/password, no SSO
- `nous` — Nous Portal OAuth

If your dashboard is already fronted by Cloudflare, neither makes sense.
Cloudflare already authenticated the user; running them through a second
password is friction. This plugin reuses that edge auth.

## Install

This plugin needs a one-line edit to Hermes's middleware allowlist (one
file, eight lines including comments). Apply the bundled patch:

```bash
cd /path/to/hermes-agent
patch -p1 < /path/to/hermes-cloudflare-access/examples/middleware-public-prefix.patch
```

Then copy the bundled plugin into Hermes's plugin tree:

```bash
PLUGIN_DIR="$(python -c 'import hermes_cli, os; print(os.path.dirname(hermes_cli.__file__))')/../plugins/dashboard_auth/cloudflare_access"
mkdir -p "$PLUGIN_DIR"
cp src/hermes_cloudflare_access/*.py "$PLUGIN_DIR/"
cp src/hermes_cloudflare_access/plugin.yaml "$PLUGIN_DIR/"
```

Restart the dashboard. The plugin auto-loads when env vars are set
(next section).

If you prefer the user-plugin path (no edits to the bundled tree other
than the middleware patch):

```bash
mkdir -p ~/.hermes/plugins/cloudflare_access/dashboard
cp extra/user_plugin/dashboard/* ~/.hermes/plugins/cloudflare_access/dashboard/
# also copy the bundled plugin files (steps above) — both are required
```

Add to `config.yaml`:

```yaml
plugins:
  enabled:
    - cloudflare_access
```

## Configure

Two values, both available in your Cloudflare Zero Trust dashboard.

**Team subdomain** — the `<team>` in `<team>.cloudflareaccess.com`. Open
the Zero Trust dashboard; the URL is `https://one.dash.cloudflare.com/?to=/:team/...`.

**Application Audience (AUD)** — a 64-char hex string. Path:
Access → Applications → (your Hermes app) → Application configuration →
Application Audience (AUD).

`config.yaml`:

```yaml
dashboard:
  public_url: https://dashboard.example.com   # recommended
  cloudflare_access:
    team: your-team
    aud: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

Or env vars (win over config):

```bash
export HERMES_DASHBOARD_CF_ACCESS_TEAM=your-team
export HERMES_DASHBOARD_CF_ACCESS_AUD=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

## Run

```bash
hermes dashboard --host 0.0.0.0 --port 9119
```

The auth gate engages automatically on non-loopback bind. The plugin
registers itself when both `team` and `aud` are set.

## How the login flow works

1. Browser hits `https://dashboard.example.com`.
2. Cloudflare edge checks the Access policy. If the user isn't logged in
   at the edge, it serves the Cloudflare login (email OTP, Google, etc).
3. Once authenticated, Cloudflare injects `Cf-Access-Jwt-Assertion` and
   `CF_Authorization` on every request through the tunnel.
4. Hermes's gate sees no Hermes session, redirects to
   `/auth/login?provider=cloudflare_access`.
5. Login page shows "Sign in with Cloudflare Access". Click.
6. Plugin redirects to `/api/plugins/cloudflare_access/callback`.
7. Callback reads the JWT, verifies the RS256 signature against the team
   JWKS at `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`,
   checks `aud` matches config, mints a Hermes session.
8. 302 to `/`. Logged in.

## Security

- **JWKS cache: 5 minutes.** Cloudflare rotates keys slowly. The cache
  avoids a network roundtrip on every request.
- **`aud` claim is mandatory.** A token issued for a different Access
  app in the same team fails verification.
- **`iss` is checked.** The team URL must match exactly.
- **`exp` / `nbf` are checked.** Standard JWT semantics.
- **Session cookies are HMAC-signed with a random 32-byte secret.** A
  fresh secret is generated per process if you don't set
  `dashboard.cloudflare_access.secret`. Set it explicitly for stable
  sessions across restarts / workers.
- **The route `/api/plugins/cloudflare_access/` is in Hermes's public
  allowlist.** The route verifies the JWT itself before doing anything
  privileged, so this is safe.

## What it isn't

- Not a replacement for the Access policy. Set up the policy in the
  Zero Trust dashboard first.
- Not a "skip Cloudflare" mode. If Access isn't in front, the JWT
  header doesn't exist and the route 401s. The plugin won't fall back
  to anything else.

## Limitations

- The middleware allowlist edit is manual. There's no plugin-contributed
  public-path API in Hermes 0.20.0. PR upstream to add one.
- JWKS cache is per-process. Multi-worker setups each fetch once on
  startup. Fine in practice.
- No refresh flow. The Access JWT is the source of truth; when it
  expires, the user re-auths at the edge. Cloudflare tokens typically
  last 24h.

## Tests

```bash
pip install -e .[test]
pytest tests/
```

Tests use a synthetic-JWT shim (`verify_access_jwt` is patched) so they
don't need a real Cloudflare team.

## License

MIT. See LICENSE.
