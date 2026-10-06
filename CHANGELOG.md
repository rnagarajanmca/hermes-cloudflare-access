# Changelog

All notable changes to `hermes-cloudflare-access` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-10-06

### Added

- `CloudflareAccessAuthProvider` — registers as a `DashboardAuthProvider`
  subclass. Trusts the `Cf-Access-Jwt-Assertion` request header (falls
  back to the `CF_Authorization` cookie) set by Cloudflare's edge, verifies
  the RS256 signature against the team JWKS at
  `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`, checks the
  `aud` / `iss` / `exp` / `nbf` claims, and mints a Hermes session.
- FastAPI route at `GET /api/plugins/cloudflare_access/callback` that
  reads the JWT, runs verification, and sets the session cookies
  (`hermes_session_at`, `hermes_session_rt`, `hermes_session_provider`).
- JWKS cache (5-minute TTL) — process-wide, auto-refreshes on key
  rotation, falls back to the previous keys on a transient Cloudflare
  error.
- 5-minute-config example with all required env vars / config keys
  documented in the README.
- 9 pytest tests covering provider registration, env-based config,
  route behaviour (no-JWT, bad-JWT, valid-JWT via header, valid-JWT via
  cookie), end-to-end `/api/auth/me` round-trip, `next=` query
  parameter, off-origin `next=` rejection.
- GitHub Actions CI matrix on Python 3.10 / 3.11 / 3.12.
- A patch file (`examples/middleware-public-prefix.patch`) documenting
  the one-line middleware allowlist edit users need to apply.

[0.1.0]: https://github.com/rnagarajanmca/hermes-cloudflare-access/releases/tag/v0.1.0
