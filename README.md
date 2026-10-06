<p align="center">
  <a href="https://github.com/rnagarajanmca/hermes-cloudflare-access/releases/tag/v0.1.0"><img src="https://img.shields.io/github/v/release/rnagarajanmca/hermes-cloudflare-access?style=flat-square" alt="Release"></a>
  <a href="https://github.com/rnagarajanmca/hermes-cloudflare-access/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow-status/rnagarajanmca/hermes-cloudflare-access/tests.yml?branch=main&style=flat-square" alt="CI"></a>
  <a href="https://github.com/rnagarajanmca/hermes-cloudflare-access/blob/main/LICENSE"><img src="https://img.shields.io/github/license/rnagarajanmca/hermes-cloudflare-access?style=flat-square" alt="License: MIT"></a>
  <a href="https://github.com/rnagarajanmca/hermes-cloudflare-access/stargazers"><img src="https://img.shields.io/github/stars/rnagarajanmca/hermes-cloudflare-access?style=flat-square" alt="Stars"></a>
  <a href="https://github.com/rnagarajanmca/hermes-cloudflare-access/issues"><img src="https://img.shields.io/github/issues/rnagarajanmca/hermes-cloudflare-access?style=flat-square" alt="Issues"></a>
  <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=flat-square&logo=python&logoColor=orange" alt="Python 3.10–3.12">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://img.shields.io/badge/Hermes%20Agent-NousResearch-6f42c1?style=flat-square" alt="Hermes Agent"></a>
</p>

# hermes-cloudflare-access

> Dashboard auth provider for [Hermes Agent](https://hermes-agent.nousresearch.com/) that trusts Cloudflare Access (Zero Trust) JWTs.

If you run Hermes behind a Cloudflare Tunnel with an Access policy on the hostname, this plugin skips Hermes's own password flow entirely. Cloudflare handles auth at the edge (email OTP, Google, Okta, whatever you wire up), and this plugin turns the validated JWT into a Hermes session cookie in one redirect.

```
browser --CF-Access-JWT--> hermes --session--> browser
   ^
   | email OTP / IdP
cloudflare edge
```

## Contents

- [Why](#why)
- [Install](#install)
- [Configure](#configure)
- [Run](#run)
- [How the login flow works](#how-the-login-flow-works)
- [Security](#security)
- [Limitations](#limitations)
- [Why pick this over `basic` / `nous`](#why-pick-this-over-basic--nous)
- [Tests](#tests)
- [Contributing](#contributing)
- [Security disclosures](#security-disclosures)
- [License](#license)

## Why

Hermes ships with two dashboard auth options:

- `basic` — username / password, no SSO
- `nous` — Nous Portal OAuth

If your dashboard is already fronted by Cloudflare, neither makes sense. Cloudflare already authenticated the user; running them through a second password is friction. This plugin reuses that edge auth — Cloudflare says "yes", Hermes says "yes", done.

## Install

The plugin lives on PyPI (recommended) and as source on GitHub:

```bash
pip install hermes-cloudflare-access
```

Or from source:

```bash
git clone https://github.com/rnagarajanmca/hermes-cloudflare-access.git
cd hermes-cloudflare-access
pip install -e .
```

Hermes itself isn't aware of the plugin's callback path until you patch one file (eight lines including comments). Apply the bundled patch:

```bash
cd /path/to/hermes-agent
patch -p1 < /path/to/hermes-cloudflare-access/examples/middleware-public-prefix.patch
```

Copy the bundled plugin into Hermes's plugin tree:

```bash
PLUGIN_DIR="$(python -c 'import hermes_cli, os; print(os.path.dirname(hermes_cli.__file__))')/../plugins/dashboard_auth/cloudflare_access"
mkdir -p "$PLUGIN_DIR"
cp src/hermes_cloudflare_access/*.py "$PLUGIN_DIR/"
cp src/hermes_cloudflare_access/plugin.yaml "$PLUGIN_DIR/"
```

If you'd rather use the user-plugin path (no edits to the bundled tree other than the middleware patch):

```bash
mkdir -p ~/.hermes/plugins/cloudflare_access/dashboard
cp extra/user_plugin/dashboard/* ~/.hermes/plugins/cloudflare_access/dashboard/
# also copy the bundled plugin files (the cp commands above) — both are required
```

Then enable it in `config.yaml`:

```yaml
plugins:
  enabled:
    - cloudflare_access
```

Restart the dashboard and the plugin auto-loads when its config is set.

## Configure

Two values, both available in your Cloudflare Zero Trust dashboard.

**Team subdomain** — the `<team>` in `<team>.cloudflareaccess.com`. Open the Zero Trust dashboard; the URL is `https://one.dash.cloudflare.com/?to=/:team/...`.

**Application Audience (AUD)** — a 64-char hex string. Path: Access → Applications → (your Hermes app) → Application configuration → Application Audience (AUD).

`config.yaml`:

```yaml
dashboard:
  public_url: https://dashboard.example.com   # recommended
  cloudflare_access:
    team: your-team
    aud: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

Or env vars (win over `config.yaml`):

```bash
export HERMES_DASHBOARD_CF_ACCESS_TEAM=your-team
export HERMES_DASHBOARD_CF_ACCESS_AUD=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Optional:

| Key | Env | Default | Notes |
|---|---|---|---|
| `dashboard.cloudflare_access.ttl_seconds` | `HERMES_DASHBOARD_CF_ACCESS_TTL_SECONDS` | `43200` (12h) | Hermes session TTL. |
| `dashboard.cloudflare_access.secret` | `HERMES_DASHBOARD_CF_ACCESS_SECRET` | random per-process | HMAC secret for the cookie. Set explicitly for stable sessions across restarts / workers. Accepts base64, hex, or raw UTF-8 (≥16 bytes). |

## Run

```bash
hermes dashboard --host 0.0.0.0 --port 9119
```

The auth gate engages automatically on non-loopback bind. The plugin registers itself when both `team` and `aud` are set. You should see a startup line like:

```
dashboard-auth-cf-access: registered provider (team=your-team, aud=0123456789ab…)
```

The login page at `/auth/login` will show a **Sign in with Cloudflare Access** button.

## How the login flow works

1. Browser hits `https://dashboard.example.com`.
2. Cloudflare edge checks the Access policy. If the user isn't logged in at the edge, it serves the Cloudflare login (email OTP, Google, etc).
3. Once authenticated, Cloudflare injects `Cf-Access-Jwt-Assertion` and `CF_Authorization` on every request through the tunnel.
4. Hermes's gate sees no Hermes session, redirects to `/auth/login?provider=cloudflare_access`.
5. Login page shows **Sign in with Cloudflare Access**. Click.
6. Plugin redirects to `/api/plugins/cloudflare_access/callback`.
7. Callback reads the JWT, verifies the RS256 signature against the team JWKS at `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`, checks `aud` matches config, mints a Hermes session.
8. 302 to `/`. Logged in.

## Security

- **JWKS cache: 5 minutes.** Cloudflare rotates keys slowly. The cache avoids a network roundtrip on every request. On refresh failure the previous keys are served (fail-open on stale).
- **`aud` claim is mandatory.** A token issued for a different Access app in the same team fails verification.
- **`iss` is checked.** The team URL must match exactly.
- **`exp` / `nbf` are checked.** Standard JWT semantics.
- **Session cookies are HMAC-signed with a 32-byte secret.** A fresh secret is generated per process if you don't set `dashboard.cloudflare_access.secret`. Set it explicitly for stable sessions across restarts / workers.
- **The route `/api/plugins/cloudflare_access/` is in Hermes's public allowlist.** The route verifies the JWT itself before doing anything privileged, so this is safe.
- **`next=` is sanitised** — only same-origin paths are honoured.

Threat model and reporting: see [`SECURITY.md`](SECURITY.md).

## Limitations

- The middleware allowlist edit is manual. There's no plugin-contributed public-path API in Hermes 0.20.0. [PR upstream](https://github.com/NousResearch/hermes-agent) to add one.
- JWKS cache is per-process. Multi-worker setups each fetch once on startup. Fine in practice.
- No refresh flow. The Access JWT is the source of truth; when it expires, the user re-auths at the edge. Cloudflare tokens typically last 24h.

## Why pick this over `basic` / `nous`

| | `basic` (password) | `nous` (OAuth) | `cloudflare_access` (this plugin) |
|---|---|---|---|
| SSO via Cloudflare Access policy | ❌ | ❌ | ✅ |
| Reuses existing edge IdP (Google, Okta, etc.) | ❌ | ❌ | ✅ |
| Hermes-side password / OAuth round-trip | ✅ | ✅ | ❌ |
| Set-up effort | trivial | trivial | one patch + two config values |
| Best when | single-user / dev | team already on Nous Portal | dashboard already on Cloudflare |

## Tests

```bash
pip install -e ".[test]"
pytest tests/
```

The test suite uses a synthetic-JWT shim (`verify_access_jwt` is patched) so it doesn't need a real Cloudflare team. CI runs on Python 3.10, 3.11, and 3.12 against `NousResearch/hermes-agent` installed editable — see `.github/workflows/tests.yml`.

## Contributing

Bug reports, feature requests, and PRs welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for dev setup, commit style, and the PR checklist.

## Security disclosures

Open a [private security advisory](https://github.com/rnagarajanmca/hermes-cloudflare-access/security/advisories/new). Do not file public issues for suspected vulnerabilities. See [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE).
