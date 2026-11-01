# Packaging and release

The wheel ships the built web UI so `schemalens serve` works after a plain
`pip install schemalens`.

## Build the wheel

```bash
# 1. Build the UI (API mode: it fetches /api/bundle at runtime)
cd web
npm ci
npm run build

# 2. Copy the build into the package (bundle.json is runtime data, not shipped)
cd ..
rm -rf src/schemalens/web_dist
mkdir -p src/schemalens/web_dist
cp -r web/dist/* src/schemalens/web_dist/
rm -f src/schemalens/web_dist/bundle.json

# 3. Build the wheel (hatch force-includes web_dist)
python -m build
```

`pyproject.toml` force-includes `src/schemalens/web_dist` in the wheel via
`[tool.hatch.build.targets.wheel.force-include]`, so the directory is shipped
even though it is git-ignored.

## Publish

```bash
# TestPyPI first
python -m twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ schemalens

# then PyPI
python -m twine upload dist/*
```

## Deploy the static demo (Vercel)

The static demo needs a `bundle.json` baked in at build time. Generate it from a
scan, then deploy `web/` with the committed `web/vercel.json`:

```bash
# produce the demo data (optionally run `schemalens explain --all` first so the
# demo ships cached explanations)
schemalens scan --dsn "$DSN" --search-path "public,bench"
schemalens export --out web/public          # writes web/public/bundle.json

# deploy (Vercel builds with VITE_DATA_MODE=static)
cd web
vercel deploy --prod
```

`bundle.json` is git-ignored for day-to-day development; for the deploy either
commit it on a release branch or generate it in the Vercel build step. In static
mode the UI loads `/bundle.json` and shows only cached explanations (generation
is disabled).

## Use the MCP server in Kiro

Add this to `.kiro/settings/mcp.json` (workspace) or `~/.kiro/settings/mcp.json`
(global), after running a scan so `schemalens.db` exists:

```json
{
  "mcpServers": {
    "schemalens": {
      "command": "schemalens",
      "args": ["mcp", "--db", "./schemalens.db"],
      "disabled": false,
      "autoApprove": ["search_schema", "describe_table", "explain_function", "get_lineage"]
    }
  }
}
```

Then ask Kiro questions like "which functions write to the rental table?" and it
will answer from the scanned metadata.
