# Changelog

All notable changes to `hermes-cloudflare-access` are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1] — 2026-10-06

### Fixed

- CI workflow now installs the plugin to **both** hermes-agent load paths
  (`plugins/cloudflare_access/dashboard/` for the dashboard plugin shim that
  mounts the FastAPI route, and `plugins/dashboard_auth/cloudflare_access/`
  for the auth provider that registers the JWT verifier and JWKS cache).
  Previous release was missing one of these and the test suite was
  failing on GitHub Actions.
- CI workflow applies the `examples/middleware-public-prefix.patch` to the
  hermes-agent clone before running tests, so the auth gate's public
  prefix list contains `/api/plugins/cloudflare_access/` and the callback
  route is reachable.
- CI workflow pins hermes-agent to commit `a31be48` instead of tracking
  `main`, so the test target doesn't move.
- CI workflow dropped Python 3.10 from the test matrix (hermes-agent
  `a31be48` requires Python >= 3.11). The plugin's own `pyproject.toml`
  still says `python>=3.10` — users on 3.10 can install the package
  directly; they just can't run the test suite (which needs hermes-agent).
- Test fixture: smoke-import check verifies the bundled and pip-installed
  provider classes share the public surface, not identity (they're
  different module objects on different file paths).
- Lint and format: replaced bare `except Exception: pass` with logged
  typed excepts in the middleware-patching test fixture; added
  `import logging` and module-level logger.
- Lint config: `BLE001` and `S110` per-file-ignored under `tests/*` so
  the patterns used by the upstream hermes-agent test fixtures don't
  fight with the lint job.
- Removed debug print statements from the test fixture.

### Changed

- The release wheel now passes `hermes verify --skip-start` end-to-end
  (bootstrap + test phases) and the CI pipeline turns green on both
  Python 3.11 and 3.12.

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
- GitHub Actions CI matrix on Python 3.11 / 3.12.
- A patch file (`examples/middleware-public-prefix.patch`) documenting
  the one-line middleware allowlist edit users need to apply.

[0.1.1]: https://github.com/rnagarajanmca/hermes-cloudflare-access/releases/tag/v0.1.1
[0.1.0]: https://github.com/rnagarajanmca/hermes-cloudflare-access/releases/tag/v0.1.0
