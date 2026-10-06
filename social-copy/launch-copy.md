# Launch social copy

Drop-in drafts for X / Twitter, Reddit (r/selfhosted, r/Hermes), and Hacker News (Show HN).

All copy is keyed off the messaging framework in `MARKETING-hermes-cloudflare-access.md` Section 3.
Voice: crisp, no marketing fluff, demo-first, short. Length tuned to each platform.

---

## X / Twitter — 5-tweet thread

> Attach `assets/login-flow.png` (or .gif) to the first tweet.

**Tweet 1**

```
Released hermes-cloudflare-access — a dashboard auth provider for Hermes Agent that trusts Cloudflare Access JWTs.

If your Hermes dashboard is already behind a Cloudflare Tunnel with an Access policy, this skips Hermes's own password flow entirely. Cloudflare auths the user, Hermes trusts it.

[attach screenshot]
```

**Tweet 2**

```
How it works:

browser → Cloudflare edge (email OTP / Google / Okta) → Cf-Access-Jwt-Assertion → hermes → session cookie → 302 to /

The plugin verifies RS256 against the team JWKS (5-min in-process cache), checks aud + iss + exp + nbf, mints the same HMAC session as basic/nous.
```

**Tweet 3**

```
Install:

  pip install hermes-cloudflare-access

Then one 8-line patch (examples/middleware-public-prefix.patch), set team + aud, restart.

Works alongside Hermes's existing basic / nous providers — register-only if both team and aud are set.
```

**Tweet 4**

```
Why this exists: Hermes ships with two dashboard auth options (basic password, nous OAuth). Neither reuses an existing Cloudflare Access policy. Running a second password on top of an already-edge-authenticated session is friction.

This is the third option.
```

**Tweet 5**

```
Repo: github.com/rnagarajanmca/hermes-cloudflare-access
v0.1.0, MIT, Python 3.10-3.12, test coverage in tests/, CI green.

Bug reports + PRs welcome.
```

**Single-tweet fallback (if the thread won't fly)**

```
hermes-cloudflare-access — a dashboard auth plugin for Hermes Agent that trusts Cloudflare Access JWTs. Skip Hermes's password when the edge has already authenticated.

pip install hermes-cloudflare-access

github.com/rnagarajanmca/hermes-cloudflare-access
```

---

## Reddit — r/selfhosted

> Cross-post also to r/Hermes (smaller, plugin-targeted) and r/CloudFlare (cross-section).

**Title**

```
Show & Tell: hermes-cloudflare-access — dashboard auth for Hermes Agent that reuses your existing Cloudflare Access policy
```

**Body**

```
Short version: if you self-host [Hermes Agent](https://hermes-agent.nousresearch.com/) and you've already got it behind a Cloudflare Tunnel with an Access policy, this plugin turns the edge auth into a Hermes session — no second password.

Repo: https://github.com/rnagarajanmca/hermes-cloudflare-access
v0.1.0, MIT, Python 3.10+.

**The problem it solves**

Hermes ships with two dashboard auth options: `basic` (username/password) and `nous` (Nous Portal OAuth). If you're running behind Cloudflare with an Access policy, you've already authenticated the user at the edge — making them enter a second password (or do an OAuth dance) is friction. This plugin is the third option, and it just trusts the `Cf-Access-Jwt-Assertion` header that Access injects.

**How it works**

1. Browser hits your Cloudflare-fronted Hermes dashboard.
2. Cloudflare Access handles auth (email OTP, Google, Okta, whatever you configured).
3. Access injects `Cf-Access-Jwt-Assertion` on every request through the tunnel.
4. Plugin verifies the RS256 signature against the team JWKS (`https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`, 5-min in-process cache).
5. Checks `aud` (mandatory), `iss` (team URL), `exp`, `nbf`.
6. Mints a Hermes session with the same HMAC scheme the other providers use.
7. 302 to `/`.

**Install**

```
pip install hermes-cloudflare-access
```

Then apply one 8-line middleware allowlist patch from the repo (`examples/middleware-public-prefix.patch` — Hermes 0.20.0 doesn't yet have a plugin-contributed public-path API; upstream PR pending), copy the bundled plugin into your Hermes plugin tree, set `team` + `aud`, restart. Full instructions in the README.

**Security notes**

- 5-min JWKS cache; serves stale keys on refresh failure rather than locking everyone out.
- `aud` is mandatory — a token for a different Access app in the same team fails.
- `iss` is checked — team URL must match.
- Session cookies are HMAC-signed; set `dashboard.cloudflare_access.secret` explicitly if you run more than one worker.
- `/api/plugins/cloudflare_access/` is in Hermes's public allowlist, but the route verifies the JWT before doing anything privileged.

**Known limitations**

- Manual middleware patch until Hermes exposes the public-path hook.
- JWKS cache is per-process (multi-worker setups each fetch once on startup).
- No token-refresh; when the Access JWT expires the user re-auths at the edge (typically 24h).

Happy to answer questions. PRs and bug reports welcome.
```

---

## Hacker News — Show HN

**Title**

```
Show HN: hermes-cloudflare-access – Cloudflare Access as Hermes Agent dashboard auth
```

**First comment (post immediately, before any reply)**

```
Author here. This is a small plugin for [Hermes Agent](https://hermes-agent.nousresearch.com/) (an open-source agent runtime from Nous Research) that turns Cloudflare Access JWTs into Hermes dashboard sessions.

Background: Hermes ships with two dashboard auth providers, `basic` (username/password) and `nous` (Nous Portal OAuth). If your Hermes dashboard is already fronted by a Cloudflare Tunnel and Access policy, you've already authenticated the user at the edge — making them run through a second password is friction. This plugin is the third option: it trusts the `Cf-Access-Jwt-Assertion` header that Cloudflare injects on every request through the tunnel, verifies it against the team JWKS, and mints a Hermes session cookie.

Implementation notes:
- Pure-Python, no new heavy deps (`cryptography`, `pyjwt`, `httpx` are already standard).
- 5-min in-process JWKS cache; serves stale keys on refresh failure (Cloudflare rotates keys slowly).
- Strict claim validation: `aud` (mandatory), `iss` (exact team URL match), `exp`, `nbf`.
- Same HMAC session scheme the other providers use; no parallel auth system to learn.
- Test suite with synthetic-JWT shim so it doesn't need a real Cloudflare team to run.

The single friction point right now is that Hermes 0.20.0 doesn't expose a plugin-contributed public-path API, so install needs an 8-line middleware allowlist patch. The patch is diff-ready in the repo; an upstream PR to add the hook is the natural next step.

Repo: https://github.com/rnagarajanmca/hermes-cloudflare-access
MIT, Python 3.10+, v0.1.0 tagged.

Happy to answer technical questions.
```

**Canned reply to the predictable "why not just disable the auth gate" comment**

```
Cloudflare's Access policy is what keeps the dashboard off the public internet. Disabling Hermes's auth gate without Access means anyone on the internet can hit the dashboard. With Access + this plugin, you get edge auth (the policy decides who gets through) and a verified Hermes session inside (the dashboard can rely on the cookie). The two layers aren't redundant — they're at different boundaries.

(If you don't have Access in front, this plugin won't help you; that's not its job. You'd want the upstream `basic` or `nous` provider, or VPN-only access.)
```

**Canned reply to the predictable "why not use Cloudflare's OIDC" comment**

```
Access doesn't expose a vanilla OIDC ID token. The header it injects (`Cf-Access-Jwt-Assertion`) is a custom JWT format with a custom JWKS endpoint. There's no off-the-shelf OIDC integration for Access — the plugin exists because OIDC isn't an option here. (Some teams use Cloudflare Tunnel + a separate IdP for app auth; that's a different architecture.)
```