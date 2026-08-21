# Public Release Checklist

Use this checklist before pushing a public branch to GitHub.

## Source Control

- [ ] Work on a dedicated public branch, for example `public-template`.
- [ ] Keep the private production remote separate from the public GitHub remote.
- [ ] Push only the reviewed public branch to GitHub.
- [ ] Do not use `git add .` when private artifacts are present.

## Files That Must Stay Private

- [ ] `.env`
- [ ] `mcp_server/.env`
- [ ] database dumps such as `*_dump.sql`
- [ ] backups and Git bundles
- [ ] reports and generated evidence workbooks
- [ ] local `outputs/`, `reports/`, and `backups/`
- [ ] screenshots or documents containing customer data

## Public Configuration

- [ ] `.env.example` contains placeholders only.
- [ ] `mcp_server/.env.example` contains placeholders only.
- [ ] README explains the Flask/MCP secret boundary.
- [ ] onboarding docs explain company-specific configuration.
- [ ] default namespaces are generic and configurable.

## Secret Scan

Run a text scan before commit:

```bash
rg -n "(sk-|api[_-]?key|secret|password|token|mongodb://|postgresql://|mysql://|bearer)" \
  -g '!node_modules/**' \
  -g '!outputs/**' \
  -g '!reports/**' \
  -g '!backups/**' \
  .
```

Expected hits should be placeholders, documentation, tests, or environment
variable names. Investigate anything that looks like a real credential.

If a real key was ever committed or shared, rotate it. Removing it from the
latest commit is not enough.

## Verification

- [ ] `git status --short` shows only intentional public changes.
- [ ] `git ls-files .env mcp_server/.env` returns no files.
- [ ] `git ls-files | rg "(^|/)(outputs|reports|backups)/|_dump\\.sql$"` returns
      no private artifacts.
- [ ] focused tests pass:

```bash
.venv/bin/python -m unittest tests.test_ioa_v3_workflow -v
```

## Publish

Recommended flow:

```bash
git add .gitignore README.md .env.example mcp_server/.env.example docs/COMPANY_ONBOARDING.md docs/PUBLIC_RELEASE_CHECKLIST.md docs/SECURITY.md
git commit -m "Prepare public product template"
git push github public-template
```

After push, review the branch on GitHub before making it the default branch or
opening a pull request into `main`.
