# Security

## Reporting a vulnerability

Please report security issues privately via GitHub:
https://github.com/rnagarajanmca/hermes-cloudflare-access/security/advisories/new

Do not file a public GitHub issue for security bugs. Expect an acknowledgement
within 72 hours.

## Supported versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | Yes (current)      |

## Threat model

The plugin's threat model assumes:

- Cloudflare's edge is trusted to authenticate users and inject a
  valid `Cf-Access-Jwt-Assertion` (or `CF_Authorization` cookie)
  on requests that pass the Access policy.
- The hermes-agent dashboard bind is not directly reachable from the
  internet without going through Cloudflare's edge. (Cloudflare
  Access enforces this; if you also expose the dashboard to a private
  network, treat that network as untrusted.)
- The operator keeps `dashboard.cloudflare_access.secret`
  (or `HERMES_DASHBOARD_CF_ACCESS_SECRET`) set to a high-entropy value
  for multi-worker / restart-surviving sessions.

The plugin does **not** defend against:

- A compromised Cloudflare team — if an attacker can mint Access JWTs
  for your team, they can mint Hermes sessions. This is a Cloudflare
  problem, not a plugin problem.
- A compromised hermes-agent host — anyone with code-exec on the
  dashboard server can read the secret and forge sessions.
- A bypass of the Access policy — if the policy is misconfigured so
  the dashboard bind is reachable without going through the edge,
  the route's `auth_required=True` flag refuses to start the server,
  so this is caught at startup.

## Cryptography

- JWTs are verified with `RS256` via the `cryptography` library.
- JWKS is fetched over HTTPS from Cloudflare's CDN.
- Session cookies are signed with `HMAC-SHA256` using a 32-byte
  secret. A fresh per-process secret is generated if no explicit
  secret is configured.

## Dependencies

`requirements.txt` pins minimum versions:

- `cryptography>=42.0`
- `httpx>=0.27`
- `fastapi>=0.110`
- `pyjwt>=2.8`

These are conservative lower bounds. The CI matrix tests against
Python 3.10 / 3.11 / 3.12 and the latest available patch release of
each dependency.
