# PyPI submission runbook

This is the only piece of distribution that requires your action.
Total time: ~10 minutes.

## 1. Create a PyPI account

1. Open https://pypi.org/account/register/
2. Verify your email
3. Enable 2FA (required to upload)
4. Go to https://pypi.org/manage/account/ and copy your username (you'll need it for step 2)

## 2. Create the API token

1. Go to https://pypi.org/manage/account/token/
2. Click **Add API token**
3. **Token name:** `hermes-cloudflare-access-upload` (or whatever you want)
4. **Scope:** "Project: hermes-cloudflare-access" — **not** "Entire account"
   (this is a security best practice; the token can only upload to this
   one project)
5. **Important:** copy the token immediately — PyPI shows it ONCE
6. Save the token somewhere you'll remember (password manager)

## 3. Reserve the project name (one-time, ~30 seconds)

1. Go to https://pypi.org/project/register/
2. Form fields:
   - **Project Name:** `hermes-cloudflare-access`
   - **Owner:** your PyPI username
3. Click **Reserve**

The project now exists as an empty placeholder. You can't reserve a name
that's already taken — if this step fails, the name is in use by someone
else and you need to pick a different name.

## 4. Upload the wheel + sdist (~30 seconds)

The artifacts are already built at:

```
/root/projects/hermes-cloudflare-access/dist/
  ├── hermes_cloudflare_access-0.1.0-py3-none-any.whl
  └── hermes_cloudflare_access-0.1.0.tar.gz
```

If you ever need to rebuild (e.g. after editing the source), run from
`/root/projects/hermes-cloudflare-access/`:

```bash
.venv/bin/python -m build
```

**Option A — upload from this box (one-shot, requires scp / ssh access):**

```bash
# from your Mac, copy the artifacts to a local dir:
scp ngserver3:/root/projects/hermes-cloudflare-access/dist/* ./dist/

# upload with the token:
python3 -m pip install --upgrade twine
python3 -m twine upload dist/* \
  --username __token__ \
  --password "pypi-XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
```

**Option B — upload directly from this box (no copy):**

Run this command on ngserver3 (it'll prompt for your token):

```bash
cd /root/projects/hermes-cloudflare-access
.venv/bin/python -m twine upload dist/* \
  --repository pypi \
  --username __token__
# paste the pypi-XXXXXXXXX token when prompted
```

## 5. Verify the upload

1. Visit https://pypi.org/project/hermes-cloudflare-access/ — you should see
   the v0.1.0 release with the README rendered
2. Test the install from anywhere:
   ```bash
   pip install --user hermes-cloudflare-access
   python -c "import hermes_cloudflare_access; print('OK')"
   ```

## 6. Revoke the token (after the upload succeeds)

1. Go to https://pypi.org/manage/account/token/
2. Click **Delete** next to `hermes-cloudflare-access-upload`

The token is project-scoped, so even if it leaks between steps 4 and 6
the worst someone can do is push a v0.1.1 to your project. But revoke
it anyway — defense in depth.

## After PyPI: link the badge

Once the package is on PyPI, add the badge to your README so visitors see
the install count. Replace the current badge line with:

```markdown
  <a href="https://pypi.org/project/hermes-cloudflare-access/"><img src="https://img.shields.io/pypi/v/hermes-cloudflare-access?style=flat-square" alt="PyPI"></a>
```

This goes right after the existing release badge. I can do this for you
once the package is on PyPI.

## What if PyPI rejects the upload?

Common reasons:

- **Project name already taken** — pick a different name in `pyproject.toml`,
  rebuild, retry
- **Version already exists** — bump to `0.1.1` in `pyproject.toml`, rebuild,
  retry
- **README fails to render** — Twine will tell you; the issue is usually
  bad markdown
- **403 / "user not allowed to upload"** — your token is project-scoped
  but you may not be listed as a project maintainer. Check
  https://pypi.org/manage/projects/hermes-cloudflare-access/

If you hit a wall, paste me the error and I'll debug.
