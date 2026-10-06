# Assets

Drop images referenced from the README here.

| File | Used by | Status |
|---|---|---|
| `banner.png` | README hero (top-of-page banner) | TODO — replace the broken `assets/banner.png` reference with a 1280×320 dark+amber banner that matches the Hermes design system (`--midground: #ffac02`, `--background-base: #170d02`). |
| `login-flow.png` | README "How the login flow works" section + social copy | ✅ Captured from the live atlas-profile install with `cloudflare_access` as the only registered provider. |

## Capturing a fresh `login-flow.png`

The dashboard renders its SPA login page at `/login`. The provider buttons are populated from `DashboardAuthProvider.registry`. To capture a screenshot showing `cloudflare_access`:

```bash
# 1. Disable every other provider in the test profile so only cloudflare_access remains.
# 2. Start the dashboard:
hermes dashboard --host 0.0.0.0 --port 9119 --skip-build --no-open &
# 3. Screenshot /login:
chromium --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --window-size=1280,900 \
  --screenshot=assets/login-flow.png \
  --virtual-time-budget=4000 \
  'http://127.0.0.1:9119/login'
```

To show all three providers (`basic` + `nous` + `cloudflare_access`) side-by-side, register all of them and re-capture.