# Add hermes-cloudflare-access to Plugins

> PR body for the `0xNyk/awesome-hermes-agent` PR. Use exactly this text.

## What

Adds `hermes-cloudflare-access` (a new public plugin under `rnagarajanmca`) to `## Skills & Plugins → ### Plugins`.

## Entry to add

Under the existing `### Plugins` heading, alphabetically near the other auth-/dashboard-related plugins:

```
- **[beta]** [hermes-cloudflare-access](https://github.com/rnagarajanmca/hermes-cloudflare-access) by [rnagarajanmca](https://github.com/rnagarajanmca) - Dashboard auth provider that trusts Cloudflare Access (Zero Trust) JWTs. Skips Hermes's own password flow when the dashboard is fronted by a Cloudflare Tunnel with an Access policy. RS256 + aud + iss verified; same HMAC session scheme as basic/nous.
```

## Why

- The plugin fills a gap in Hermes's existing dashboard auth options. Hermes ships `basic` (password) and `nous` (Nous Portal OAuth); `cloudflare_access` is the third official-shape provider and the first that reuses edge auth.
- It already exists as a tagged public release (`v0.1.0`) with a test suite, CI matrix (3.10/3.11/3.12 against `NousResearch/hermes-agent`), an MIT license, and a `CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md`.
- Listing it makes the plugin discoverable to the 5.8k-star directory's audience, which is the canonical "where do I find a Hermes plugin" hub for the parent ecosystem.

## Checklist (per awesome-hermes-agent CONTRIBUTING)

- [x] Directly related to Hermes Agent ecosystem ✅
- [x] Clear README ✅
- [x] Reasonably maintained (active CI, v0.1.0 tag) ✅
- [x] Not a duplicate (no existing Cloudflare Access dashboard auth provider listed) ✅

Thanks for the curated list — happy to adjust formatting, status tag, or placement.