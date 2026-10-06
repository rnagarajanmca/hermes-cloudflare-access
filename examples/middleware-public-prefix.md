# Middleware patch for Hermes 0.20.0+

The plugin's `GET /api/plugins/cloudflare_access/callback` route needs to
bypass the dashboard-auth gate so it can read the `Cf-Access-Jwt-Assertion`
header (or `CF_Authorization` cookie) and mint a session.

The route is at a path that is NOT in the framework's hardcoded
`_GATE_PUBLIC_PREFIXES` list. There is no public API for plugins to extend
the list at runtime (Hermes 0.20.0); upstream may add one in a future
release, in which case this patch can be dropped.

## What to change

File: `hermes_cli/dashboard_auth/middleware.py`

Find `_GATE_PUBLIC_PREFIXES: tuple[str, ...] = (` and add one entry near
the end of the tuple, before the closing `)`. The line to add:

```python
    # cloudflare_access dashboard auth plugin.
    # Reads the Cf-Access-Jwt-Assertion header / CF_Authorization cookie
    # (set by Cloudflare's edge) and mints a Hermes session. The route
    # itself enforces auth by verifying the JWT signature + aud/iss/exp
    # against the team JWKS before doing anything privileged, so adding
    # it to the public list is safe — the gate is just bypassed so the
    # plugin's own verifier can run.
    "/api/plugins/cloudflare_access/",
```

## Or apply this patch

If you have the patch utility installed, you can apply the diff below:

```bash
cd /path/to/hermes-agent
patch -p1 < examples/middleware-public-prefix.patch
```

The patch is the actual diff I'd submit upstream if the maintainers
accept it. Review it before applying — it touches a security-sensitive
allowlist.
