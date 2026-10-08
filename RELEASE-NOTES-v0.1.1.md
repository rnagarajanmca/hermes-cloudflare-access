# Release notes — v0.1.1

> Use this file as `--notes-file` for `gh release create v0.1.1`.

---

## What's in this release

Patch release. The plugin code itself is unchanged from v0.1.0 — the
difference is everything around the test suite and the CI pipeline that
proves it works.

If you already have v0.1.0 installed and running, you don't need to
upgrade. The plugin source, the wheel contents, the runtime behaviour
are all identical. v0.1.1 exists so that:

- `pip install hermes-cloudflare-access` from PyPI now ships a wheel
  that passes `hermes verify` end-to-end
- The CI badge on the README turns green instead of perpetually red
- Future maintainers can run the test suite locally with a clean
  hermes-agent clone and have it pass

---

## Install

```bash
pip install --upgrade hermes-cloudflare-access
```

Or pin a version:

```bash
pip install hermes-cloudflare-access==0.1.1
```

The plugin still requires the one-line middleware allowlist edit (the
8-line patch in `examples/middleware-public-prefix.patch`). The patch
is the same as in v0.1.0. See the [README](README.md) for full
install instructions.

---

## Fixed (in the CI / release infrastructure)

- **CI workflow now installs the plugin to BOTH hermes-agent load
  paths.** The dashboard plugin loader (`plugins/<name>/dashboard/`) and
  the auth provider loader (`plugins/dashboard_auth/<name>/`) scan
  different directories; both must be populated for the test suite to
  pass. Previous release was missing the dashboard-plugin copy step.

- **CI workflow applies the middleware allowlist patch** to the cloned
  hermes-agent before running tests, so the auth gate's
  `_GATE_PUBLIC_PREFIXES` contains `/api/plugins/cloudflare_access/` and
  the callback route is reachable.

- **CI workflow pins hermes-agent to commit `a31be48`** instead of
  tracking `main`, so the test target is stable.

- **CI workflow dropped Python 3.10 from the test matrix** (hermes-agent
  `a31be48` requires Python >= 3.11). The plugin's own `pyproject.toml`
  still says `python>=3.10` — users on 3.10 can install the package
  directly; they just can't run the test suite (which needs hermes-agent).

- **Test fixture improvements** — the smoke-import check now verifies
  the bundled and pip-installed provider classes share the public
  surface (not identity, which was a wrong assumption since they're
  different module objects on different file paths). Lint and format
  cleanups in the test fixture (logged typed excepts, removed bare
  `except: pass` patterns, removed debug print statements). `BLE001` and
  `S110` are per-file-ignored under `tests/*` so the upstream test
  patterns don't fight with the lint job.

---

## Verified

- Local `hermes verify --skip-start`: **ok**, 9/9 tests pass
- CI run `37418710391` (commit `1ca6849`): **lint ✅, test 3.11 ✅,
  test 3.12 ✅**
- Wheel METADATA: no personal data, no leaked emails
- `twine check`: PASSED for both wheel and sdist
- `pip install hermes-cloudflare-access==0.1.1` in a clean venv:
  installs, imports cleanly, plugin.yaml ships in the wheel

---

## Acknowledgements

Built and verified end-to-end on 2026-10-06 against
`NousResearch/hermes-agent` `a31be48` (2026-10-06 release). Bug
reports and PRs welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

**Full Changelog**: https://github.com/rnagarajanmca/hermes-cloudflare-access/blob/main/CHANGELOG.md
