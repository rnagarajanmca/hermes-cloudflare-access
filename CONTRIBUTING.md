# Contributing

Thanks for your interest in `hermes-cloudflare-access`. Bug reports, feature requests, and PRs are all welcome.

## Reporting issues

Use the issue templates under `.github/ISSUE_TEMPLATE/`:

- **Bug report** — anything that misbehaves against a real or synthetic Cloudflare team.
- **Feature request** — improvements to the provider, the JWKS cache, or the install path.
- **Question** — anything that doesn't fit a bug or a feature.

Please include:

- Hermes Agent version (`python -c 'import hermes_cli; print(hermes_cli.__version__)'`).
- Plugin version (`pip show hermes-cloudflare-access`).
- Python version.
- The relevant section of `~/.hermes/logs/dashboard.log` if the issue is in the request handler.

## Development setup

```bash
git clone https://github.com/rnagarajanmca/hermes-cloudflare-access.git
cd hermes-cloudflare-access
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"
# hermes-agent is installed editable by CI; for local dev:
pip install -e /path/to/hermes-agent
```

Run tests:

```bash
pytest tests/
```

Run the linter (if installed):

```bash
ruff check src/ tests/
```

## Commit style

[Conventional Commits](https://www.conventionalcommits.org/en/v1.1.0/) (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). One logical change per commit.

## PR checklist

- [ ] Tests added or updated for the change.
- [ ] `pytest tests/` is green locally.
- [ ] `README.md` updated if install / configure / behaviour changed.
- [ ] `CHANGELOG.md` updated under an Unreleased section.
- [ ] No new third-party dependencies without discussion (the dep list is intentionally tight).

## Project structure

```
src/hermes_cloudflare_access/
  __init__.py    # CloudflareAccessAuthProvider, JWT verifier, JWKS cache, register(ctx)
  router.py      # FastAPI callback route
  plugin.yaml    # bundled-plugin descriptor
tests/
  test_cloudflare_access.py   # synthetic-JWT shim tests
examples/
  middleware-public-prefix.patch   # required until hermes exposes the hook
extra/user_plugin/dashboard/      # user-plugin install path
.github/workflows/tests.yml       # Python 3.10/3.11/3.12 CI
```

## Coding conventions

- Python 3.10+; use modern type hints (`dict[str, str]` is fine on 3.10 in this codebase, but prefer `from __future__ import annotations` if it matters).
- `httpx` for outbound HTTP (already a dep). Do not add `requests`.
- `pyjwt` for JWT decoding; `cryptography` for low-level primitives when needed.
- Prefer raising `ValueError` with a specific reason string; the framework converts these into 401s with operator-actionable messages.

## License

By contributing, you agree that your contributions are licensed under the project's [MIT](LICENSE) terms.